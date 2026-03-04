/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.apache.cassandra.auth;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.math.BigInteger;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.RSAPublicKeySpec;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.apache.cassandra.exceptions.AuthenticationException;

/**
 * Validates Microsoft Entra ID (Azure AD) JWT tokens.
 *
 * This validator:
 * 1. Fetches JSON Web Key Set (JWKS) from Microsoft's well-known endpoint
 * 2. Verifies the RS256 signature of the JWT using the matching public key
 * 3. Validates standard claims: issuer (iss), audience (aud), expiry (exp), not-before (nbf)
 * 4. Extracts user identity and group membership claims
 *
 * Uses only JDK classes and Jackson (already a Cassandra dependency) - no external JWT libraries required.
 */
public class EntraIdTokenValidator
{
    private static final Logger logger = LoggerFactory.getLogger(EntraIdTokenValidator.class);
    private static final ObjectMapper objectMapper = new ObjectMapper();

    // Cache JWKS keys with a configurable TTL (default 24 hours)
    private static final long JWKS_CACHE_TTL_MS = TimeUnit.HOURS.toMillis(24);
    private final Map<String, PublicKey> keyCache = new ConcurrentHashMap<>();
    private volatile long keyCacheLastRefresh = 0;

    private final String tenantId;
    private final String clientId;
    private final String jwksUrl;
    private final Set<String> allowedIssuers;

    // Clock skew tolerance for token expiry validation (5 minutes)
    private static final long CLOCK_SKEW_SECONDS = 300;

    public EntraIdTokenValidator(String tenantId, String clientId)
    {
        this.tenantId = tenantId;
        this.clientId = clientId;
        this.jwksUrl = String.format("https://login.microsoftonline.com/%s/discovery/v2.0/keys", tenantId);

        // Accept both v1 and v2 issuer formats
        this.allowedIssuers = new HashSet<>();
        this.allowedIssuers.add(String.format("https://login.microsoftonline.com/%s/v2.0", tenantId));
        this.allowedIssuers.add(String.format("https://sts.windows.net/%s/", tenantId));
    }

    /**
     * Validates a JWT token and returns the parsed claims.
     *
     * @param jwtToken the raw JWT token string (base64url-encoded header.payload.signature)
     * @return the validated claims from the token
     * @throws AuthenticationException if the token is invalid, expired, or has an untrusted signature
     */
    public EntraIdClaims validateToken(String jwtToken) throws AuthenticationException
    {
        try
        {
            // Split the JWT into its three parts
            String[] parts = jwtToken.split("\\.");
            if (parts.length != 3)
                throw new AuthenticationException("Invalid JWT token format: expected 3 parts, got " + parts.length);

            // Decode header and payload
            String headerJson = new String(base64UrlDecode(parts[0]), StandardCharsets.UTF_8);
            String payloadJson = new String(base64UrlDecode(parts[1]), StandardCharsets.UTF_8);
            byte[] signatureBytes = base64UrlDecode(parts[2]);

            JsonNode header = objectMapper.readTree(headerJson);
            JsonNode payload = objectMapper.readTree(payloadJson);

            // Verify the algorithm
            String alg = header.has("alg") ? header.get("alg").asText() : null;
            if (!"RS256".equals(alg))
                throw new AuthenticationException("Unsupported JWT algorithm: " + alg + ". Only RS256 is supported.");

            // Get the key ID from the header
            String kid = header.has("kid") ? header.get("kid").asText() : null;
            if (kid == null)
                throw new AuthenticationException("JWT header missing 'kid' (key ID) claim");

            // Verify the signature
            PublicKey publicKey = getSigningKey(kid);
            verifySignature(parts[0] + "." + parts[1], signatureBytes, publicKey);

            // Validate claims
            validateClaims(payload);

            // Extract and return claims
            return extractClaims(payload);
        }
        catch (AuthenticationException e)
        {
            throw e;
        }
        catch (Exception e)
        {
            logger.warn("EntraID token validation failed", e);
            throw new AuthenticationException("Failed to validate EntraID token: " + e.getMessage());
        }
    }

    /**
     * Verifies the RSA-SHA256 signature of the JWT.
     */
    private void verifySignature(String signingInput, byte[] signatureBytes, PublicKey publicKey)
        throws AuthenticationException
    {
        try
        {
            Signature sig = Signature.getInstance("SHA256withRSA");
            sig.initVerify(publicKey);
            sig.update(signingInput.getBytes(StandardCharsets.US_ASCII));
            if (!sig.verify(signatureBytes))
                throw new AuthenticationException("JWT signature verification failed");
        }
        catch (AuthenticationException e)
        {
            throw e;
        }
        catch (Exception e)
        {
            throw new AuthenticationException("Failed to verify JWT signature: " + e.getMessage());
        }
    }

    /**
     * Validates standard JWT claims: iss, aud, exp, nbf.
     */
    private void validateClaims(JsonNode payload) throws AuthenticationException
    {
        long now = System.currentTimeMillis() / 1000;

        // Validate issuer
        String issuer = payload.has("iss") ? payload.get("iss").asText() : null;
        if (issuer == null || !allowedIssuers.contains(issuer))
            throw new AuthenticationException("Invalid token issuer: " + issuer
                + ". Expected one of: " + allowedIssuers);

        // Validate audience
        String audience = payload.has("aud") ? payload.get("aud").asText() : null;
        if (!clientId.equals(audience))
            throw new AuthenticationException("Invalid token audience: " + audience
                + ". Expected: " + clientId);

        // Validate expiration
        if (payload.has("exp"))
        {
            long exp = payload.get("exp").asLong();
            if (now > exp + CLOCK_SKEW_SECONDS)
                throw new AuthenticationException("Token has expired. Expiry: " + exp + ", Current: " + now);
        }
        else
        {
            throw new AuthenticationException("Token missing 'exp' (expiry) claim");
        }

        // Validate not-before (optional but recommended)
        if (payload.has("nbf"))
        {
            long nbf = payload.get("nbf").asLong();
            if (now < nbf - CLOCK_SKEW_SECONDS)
                throw new AuthenticationException("Token not yet valid. Not-before: " + nbf + ", Current: " + now);
        }
    }

    /**
     * Extracts relevant claims from the JWT payload.
     */
    private EntraIdClaims extractClaims(JsonNode payload)
    {
        String oid = payload.has("oid") ? payload.get("oid").asText() : null;
        String preferredUsername = payload.has("preferred_username") ? payload.get("preferred_username").asText() : null;
        String upn = payload.has("upn") ? payload.get("upn").asText() : null;
        String sub = payload.has("sub") ? payload.get("sub").asText() : null;
        String name = payload.has("name") ? payload.get("name").asText() : null;

        // Extract groups (Entra ID can include group object IDs)
        Set<String> groups = new HashSet<>();
        if (payload.has("groups") && payload.get("groups").isArray())
        {
            for (JsonNode group : payload.get("groups"))
                groups.add(group.asText());
        }

        // Extract roles (app roles assigned in Entra ID)
        Set<String> roles = new HashSet<>();
        if (payload.has("roles") && payload.get("roles").isArray())
        {
            for (JsonNode role : payload.get("roles"))
                roles.add(role.asText());
        }

        return new EntraIdClaims(oid, preferredUsername, upn, sub, name, groups, roles);
    }

    /**
     * Retrieves the RSA public key for the given key ID from Microsoft's JWKS endpoint.
     * Keys are cached and refreshed periodically.
     */
    private PublicKey getSigningKey(String kid) throws AuthenticationException
    {
        // Check cache first
        PublicKey cached = keyCache.get(kid);
        if (cached != null && !isCacheExpired())
            return cached;

        // Refresh the key cache
        synchronized (this)
        {
            // Double-check after acquiring lock
            cached = keyCache.get(kid);
            if (cached != null && !isCacheExpired())
                return cached;

            refreshKeyCache();
        }

        cached = keyCache.get(kid);
        if (cached == null)
            throw new AuthenticationException("Unable to find signing key with kid: " + kid
                + " in JWKS from " + jwksUrl);

        return cached;
    }

    private boolean isCacheExpired()
    {
        return System.currentTimeMillis() - keyCacheLastRefresh > JWKS_CACHE_TTL_MS;
    }

    /**
     * Fetches JWKS from Microsoft's endpoint and populates the key cache.
     */
    private void refreshKeyCache() throws AuthenticationException
    {
        try
        {
            logger.info("Refreshing JWKS key cache from {}", jwksUrl);
            String jwksJson = fetchUrl(jwksUrl);
            JsonNode jwks = objectMapper.readTree(jwksJson);
            JsonNode keys = jwks.get("keys");

            if (keys == null || !keys.isArray())
                throw new AuthenticationException("Invalid JWKS response: missing 'keys' array");

            Map<String, PublicKey> newKeys = new HashMap<>();
            for (JsonNode key : keys)
            {
                String kid = key.has("kid") ? key.get("kid").asText() : null;
                String kty = key.has("kty") ? key.get("kty").asText() : null;
                String use = key.has("use") ? key.get("use").asText() : null;

                // Only process RSA signing keys
                if (kid != null && "RSA".equals(kty) && ("sig".equals(use) || use == null))
                {
                    try
                    {
                        String n = key.get("n").asText();
                        String e = key.get("e").asText();
                        PublicKey publicKey = buildRSAPublicKey(n, e);
                        newKeys.put(kid, publicKey);
                    }
                    catch (Exception ex)
                    {
                        logger.warn("Failed to parse RSA key with kid {}: {}", kid, ex.getMessage());
                    }
                }
            }

            keyCache.clear();
            keyCache.putAll(newKeys);
            keyCacheLastRefresh = System.currentTimeMillis();

            logger.info("JWKS key cache refreshed with {} keys", newKeys.size());
        }
        catch (AuthenticationException e)
        {
            throw e;
        }
        catch (Exception e)
        {
            throw new AuthenticationException("Failed to refresh JWKS key cache: " + e.getMessage());
        }
    }

    /**
     * Builds an RSA public key from base64url-encoded modulus (n) and exponent (e).
     */
    private static PublicKey buildRSAPublicKey(String modulusB64, String exponentB64) throws Exception
    {
        byte[] modulusBytes = base64UrlDecode(modulusB64);
        byte[] exponentBytes = base64UrlDecode(exponentB64);

        BigInteger modulus = new BigInteger(1, modulusBytes);
        BigInteger exponent = new BigInteger(1, exponentBytes);

        RSAPublicKeySpec spec = new RSAPublicKeySpec(modulus, exponent);
        KeyFactory factory = KeyFactory.getInstance("RSA");
        return factory.generatePublic(spec);
    }

    /**
     * Base64url decoding (JWT uses base64url without padding).
     */
    private static byte[] base64UrlDecode(String input)
    {
        // Java 8's Base64 URL decoder handles the padding automatically
        return Base64.getUrlDecoder().decode(input);
    }

    /**
     * Fetches content from a URL using HTTP GET.
     */
    private String fetchUrl(String urlStr) throws IOException
    {
        URL url = new URL(urlStr);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("GET");
        conn.setConnectTimeout(10000);
        conn.setReadTimeout(10000);

        try
        {
            int responseCode = conn.getResponseCode();
            if (responseCode != 200)
                throw new IOException("HTTP " + responseCode + " from " + urlStr);

            try (BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8)))
            {
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null)
                    sb.append(line);
                return sb.toString();
            }
        }
        finally
        {
            conn.disconnect();
        }
    }

    /**
     * Represents the validated claims extracted from an Entra ID JWT token.
     */
    public static class EntraIdClaims
    {
        /** The Object ID (oid) of the principal - unique identifier in Entra ID */
        public final String objectId;

        /** The preferred username (email) - may be null for service principals */
        public final String preferredUsername;

        /** The User Principal Name (UPN) - common in enterprise tokens */
        public final String upn;

        /** The subject (sub) claim - unique identifier for the user within the application */
        public final String subject;

        /** The display name of the user */
        public final String name;

        /** The set of Entra ID group Object IDs the user belongs to */
        public final Set<String> groups;

        /** The set of app roles assigned to the user in Entra ID */
        public final Set<String> roles;

        public EntraIdClaims(String objectId, String preferredUsername, String upn, String subject,
                             String name, Set<String> groups, Set<String> roles)
        {
            this.objectId = objectId;
            this.preferredUsername = preferredUsername;
            this.upn = upn;
            this.subject = subject;
            this.name = name;
            this.groups = Collections.unmodifiableSet(groups);
            this.roles = Collections.unmodifiableSet(roles);
        }

        /**
         * Determines the best available identity for use as a Cassandra role name.
         * Priority: preferred_username > upn > name > oid > sub
         */
        public String getPrincipalName()
        {
            if (preferredUsername != null && !preferredUsername.isEmpty())
                return preferredUsername;
            if (upn != null && !upn.isEmpty())
                return upn;
            if (name != null && !name.isEmpty())
                return name;
            if (objectId != null && !objectId.isEmpty())
                return objectId;
            if (subject != null && !subject.isEmpty())
                return subject;
            return null;
        }

        @Override
        public String toString()
        {
            return String.format("EntraIdClaims{oid=%s, preferred_username=%s, upn=%s, groups=%s, roles=%s}",
                                 objectId, preferredUsername, upn, groups, roles);
        }
    }
}
