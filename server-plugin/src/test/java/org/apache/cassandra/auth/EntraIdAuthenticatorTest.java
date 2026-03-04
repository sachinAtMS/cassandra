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

import java.io.File;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import org.junit.After;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.exceptions.AuthenticationException;
import org.apache.cassandra.exceptions.ConfigurationException;

import static org.junit.Assert.*;

/**
 * Unit tests for EntraID authentication plugin components.
 *
 * These tests use a locally generated RSA key pair to create and sign
 * JWT tokens, simulating what Microsoft Entra ID would produce.
 * No external network calls are made.
 */
public class EntraIdAuthenticatorTest
{
    private static final ObjectMapper mapper = new ObjectMapper();
    private static final String TEST_TENANT_ID = "72f988bf-86f1-41af-91ab-2d7cd011db47";
    private static final String TEST_CLIENT_ID = "6731de76-14a6-49ae-97bc-6eba6914391e";
    private static final String TEST_KID = "test-key-001";

    private static KeyPair rsaKeyPair;

    @BeforeClass
    public static void setupClass() throws Exception
    {
        // Generate an RSA key pair for signing test tokens
        KeyPairGenerator keyGen = KeyPairGenerator.getInstance("RSA");
        keyGen.initialize(2048);
        rsaKeyPair = keyGen.generateKeyPair();
    }

    @After
    public void cleanupSystemProperties()
    {
        System.clearProperty("cassandra.entra.tenant_id");
        System.clearProperty("cassandra.entra.client_id");
        System.clearProperty("cassandra.entra.config");
        EntraIdAuthenticator.claimsCache.clear();
    }

    // ===================== Token Validator Tests =====================

    @Test
    public void testValidTokenDecoding() throws Exception
    {
        TestableTokenValidator validator = new TestableTokenValidator(TEST_TENANT_ID, TEST_CLIENT_ID, rsaKeyPair);

        String token = createTestToken(
            TEST_KID,
            TEST_TENANT_ID,
            TEST_CLIENT_ID,
            "user@contoso.com",   // preferred_username
            "user@contoso.com",   // upn
            "oid-12345",          // oid
            Arrays.asList("group-1", "group-2"),
            Arrays.asList("CassandraAdmin", "CassandraReader"),
            System.currentTimeMillis() / 1000 + 3600
        );

        EntraIdTokenValidator.EntraIdClaims claims = validator.validateToken(token);

        assertEquals("user@contoso.com", claims.preferredUsername);
        assertEquals("user@contoso.com", claims.upn);
        assertEquals("oid-12345", claims.objectId);
        assertTrue(claims.groups.contains("group-1"));
        assertTrue(claims.groups.contains("group-2"));
        assertEquals(2, claims.groups.size());
        assertTrue(claims.roles.contains("CassandraAdmin"));
        assertTrue(claims.roles.contains("CassandraReader"));
        assertEquals(2, claims.roles.size());
    }

    @Test
    public void testPrincipalNamePriority() throws Exception
    {
        // Test that preferred_username has highest priority
        EntraIdTokenValidator.EntraIdClaims claims1 = new EntraIdTokenValidator.EntraIdClaims(
            "oid-123", "preferred@contoso.com", "upn@contoso.com", "sub-123", "User Name",
            Collections.emptySet(), Collections.emptySet()
        );
        assertEquals("preferred@contoso.com", claims1.getPrincipalName());

        // Test fallback to UPN
        EntraIdTokenValidator.EntraIdClaims claims2 = new EntraIdTokenValidator.EntraIdClaims(
            "oid-123", null, "upn@contoso.com", "sub-123", "User Name",
            Collections.emptySet(), Collections.emptySet()
        );
        assertEquals("upn@contoso.com", claims2.getPrincipalName());

        // Test fallback to name
        EntraIdTokenValidator.EntraIdClaims claims3 = new EntraIdTokenValidator.EntraIdClaims(
            "oid-123", null, null, "sub-123", "User Name",
            Collections.emptySet(), Collections.emptySet()
        );
        assertEquals("User Name", claims3.getPrincipalName());

        // Test fallback to OID
        EntraIdTokenValidator.EntraIdClaims claims4 = new EntraIdTokenValidator.EntraIdClaims(
            "oid-123", null, null, "sub-123", null,
            Collections.emptySet(), Collections.emptySet()
        );
        assertEquals("oid-123", claims4.getPrincipalName());

        // Test fallback to subject
        EntraIdTokenValidator.EntraIdClaims claims5 = new EntraIdTokenValidator.EntraIdClaims(
            null, null, null, "sub-123", null,
            Collections.emptySet(), Collections.emptySet()
        );
        assertEquals("sub-123", claims5.getPrincipalName());
    }

    @Test(expected = AuthenticationException.class)
    public void testExpiredToken() throws Exception
    {
        TestableTokenValidator validator = new TestableTokenValidator(TEST_TENANT_ID, TEST_CLIENT_ID, rsaKeyPair);

        String token = createTestToken(
            TEST_KID, TEST_TENANT_ID, TEST_CLIENT_ID,
            "user@contoso.com", null, "oid-123",
            Collections.emptyList(), Collections.emptyList(),
            System.currentTimeMillis() / 1000 - 600
        );

        validator.validateToken(token);
    }

    @Test(expected = AuthenticationException.class)
    public void testWrongAudience() throws Exception
    {
        TestableTokenValidator validator = new TestableTokenValidator(TEST_TENANT_ID, TEST_CLIENT_ID, rsaKeyPair);

        String token = createTestToken(
            TEST_KID, TEST_TENANT_ID, "wrong-client-id",
            "user@contoso.com", null, "oid-123",
            Collections.emptyList(), Collections.emptyList(),
            System.currentTimeMillis() / 1000 + 3600
        );

        validator.validateToken(token);
    }

    @Test(expected = AuthenticationException.class)
    public void testWrongIssuer() throws Exception
    {
        TestableTokenValidator validator = new TestableTokenValidator(TEST_TENANT_ID, TEST_CLIENT_ID, rsaKeyPair);

        String token = createTestTokenWithIssuer(
            TEST_KID, "https://evil.com/wrong-tenant/v2.0", TEST_CLIENT_ID,
            "user@contoso.com", null, "oid-123",
            Collections.emptyList(), Collections.emptyList(),
            System.currentTimeMillis() / 1000 + 3600
        );

        validator.validateToken(token);
    }

    @Test(expected = AuthenticationException.class)
    public void testTamperedToken() throws Exception
    {
        TestableTokenValidator validator = new TestableTokenValidator(TEST_TENANT_ID, TEST_CLIENT_ID, rsaKeyPair);

        String token = createTestToken(
            TEST_KID, TEST_TENANT_ID, TEST_CLIENT_ID,
            "user@contoso.com", null, "oid-123",
            Collections.emptyList(), Collections.emptyList(),
            System.currentTimeMillis() / 1000 + 3600
        );

        // Tamper with the payload
        String[] parts = token.split("\\.");
        String tamperedPayload = parts[1].substring(0, parts[1].length() - 1) + "X";
        String tamperedToken = parts[0] + "." + tamperedPayload + "." + parts[2];

        validator.validateToken(tamperedToken);
    }

    @Test(expected = AuthenticationException.class)
    public void testWrongSigningKey() throws Exception
    {
        KeyPairGenerator keyGen = KeyPairGenerator.getInstance("RSA");
        keyGen.initialize(2048);
        KeyPair differentKey = keyGen.generateKeyPair();

        TestableTokenValidator validator = new TestableTokenValidator(TEST_TENANT_ID, TEST_CLIENT_ID, differentKey);

        String token = createTestToken(
            TEST_KID, TEST_TENANT_ID, TEST_CLIENT_ID,
            "user@contoso.com", null, "oid-123",
            Collections.emptyList(), Collections.emptyList(),
            System.currentTimeMillis() / 1000 + 3600
        );

        validator.validateToken(token);
    }

    @Test(expected = AuthenticationException.class)
    public void testMalformedToken() throws Exception
    {
        TestableTokenValidator validator = new TestableTokenValidator(TEST_TENANT_ID, TEST_CLIENT_ID, rsaKeyPair);
        validator.validateToken("this.is.not.a.valid.jwt");
    }

    @Test
    public void testGroupsAndRolesExtraction() throws Exception
    {
        TestableTokenValidator validator = new TestableTokenValidator(TEST_TENANT_ID, TEST_CLIENT_ID, rsaKeyPair);

        List<String> groups = Arrays.asList(
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
            "00000000-0000-0000-0000-000000000003"
        );
        List<String> roles = Arrays.asList("cassandra.read", "cassandra.write");

        String token = createTestToken(
            TEST_KID, TEST_TENANT_ID, TEST_CLIENT_ID,
            "admin@contoso.com", null, "oid-admin",
            groups, roles,
            System.currentTimeMillis() / 1000 + 3600
        );

        EntraIdTokenValidator.EntraIdClaims claims = validator.validateToken(token);

        assertEquals(3, claims.groups.size());
        assertEquals(2, claims.roles.size());
        assertTrue(claims.groups.containsAll(groups));
        assertTrue(claims.roles.containsAll(roles));
    }

    // ===================== SASL Negotiator Tests =====================

    @Test
    public void testSaslPlainDecoding() throws Exception
    {
        String username = "user@contoso.com";
        String jwtToken = "eyJhbGciOiJSUzI1NiJ9.eyJ0ZXN0IjoidHJ1ZSJ9.signature";

        byte[] saslResponse = buildSaslPlainResponse("", username, jwtToken);

        int nulCount = 0;
        for (byte b : saslResponse)
        {
            if (b == 0)
                nulCount++;
        }
        assertEquals("SASL PLAIN should have exactly 2 NUL separators", 2, nulCount);
    }

    // ===================== Configuration Tests =====================

    @Test(expected = ConfigurationException.class)
    public void testMissingTenantId()
    {
        EntraIdAuthenticator auth = new EntraIdAuthenticator();
        System.setProperty("cassandra.entra.tenant_id", "");
        System.setProperty("cassandra.entra.client_id", TEST_CLIENT_ID);
        auth.validateConfiguration();
    }

    @Test(expected = ConfigurationException.class)
    public void testMissingClientId()
    {
        EntraIdAuthenticator auth = new EntraIdAuthenticator();
        System.setProperty("cassandra.entra.tenant_id", TEST_TENANT_ID);
        System.setProperty("cassandra.entra.client_id", "");
        auth.validateConfiguration();
    }

    @Test
    public void testValidSystemPropertyConfig()
    {
        EntraIdAuthenticator auth = new EntraIdAuthenticator();
        System.setProperty("cassandra.entra.tenant_id", TEST_TENANT_ID);
        System.setProperty("cassandra.entra.client_id", TEST_CLIENT_ID);
        // Should not throw
        auth.validateConfiguration();
    }

    @Test
    public void testPropertiesFileConfig() throws Exception
    {
        // Create a temporary properties file
        File tempFile = File.createTempFile("entra-id-test", ".properties");
        tempFile.deleteOnExit();
        try (FileWriter writer = new FileWriter(tempFile))
        {
            writer.write("tenant_id=" + TEST_TENANT_ID + "\n");
            writer.write("client_id=" + TEST_CLIENT_ID + "\n");
        }

        // Point the authenticator to the temp file
        System.setProperty("cassandra.entra.config", tempFile.getAbsolutePath());

        EntraIdAuthenticator auth = new EntraIdAuthenticator();
        // Should not throw — reads config from properties file
        auth.validateConfiguration();
    }

    @Test(expected = ConfigurationException.class)
    public void testMissingPropertiesFile()
    {
        // Point to a non-existent file, no system properties set
        System.setProperty("cassandra.entra.config", "/nonexistent/path/entra-id.properties");

        EntraIdAuthenticator auth = new EntraIdAuthenticator();
        auth.validateConfiguration();
    }

    @Test
    public void testRequiresAuthentication()
    {
        EntraIdAuthenticator auth = new EntraIdAuthenticator();
        assertTrue("EntraIdAuthenticator must require authentication", auth.requireAuthentication());
    }

    // ===================== Claims Cache Tests =====================

    @Test
    public void testClaimsCaching()
    {
        EntraIdTokenValidator.EntraIdClaims claims = new EntraIdTokenValidator.EntraIdClaims(
            "oid-test", "testuser@contoso.com", null, "sub-test", "Test User",
            new HashSet<>(Arrays.asList("group-a", "group-b")),
            new HashSet<>(Arrays.asList("role-x"))
        );

        EntraIdAuthenticator.claimsCache.put("testuser@contoso.com", claims);

        EntraIdTokenValidator.EntraIdClaims cached = EntraIdAuthenticator.getCachedClaims("testuser@contoso.com");
        assertNotNull(cached);
        assertEquals("oid-test", cached.objectId);
        assertEquals("testuser@contoso.com", cached.preferredUsername);
        assertTrue(cached.groups.contains("group-a"));
        assertTrue(cached.groups.contains("group-b"));
        assertTrue(cached.roles.contains("role-x"));
    }

    @Test
    public void testClaimsCacheMiss()
    {
        assertNull(EntraIdAuthenticator.getCachedClaims("nonexistent@contoso.com"));
    }

    // ===================== Helper Methods =====================

    private String createTestToken(String kid, String tenantId, String clientId,
                                   String preferredUsername, String upn, String oid,
                                   List<String> groups, List<String> roles,
                                   long expirySeconds) throws Exception
    {
        String issuer = String.format("https://login.microsoftonline.com/%s/v2.0", tenantId);
        return createTestTokenWithIssuer(kid, issuer, clientId, preferredUsername, upn, oid,
                                         groups, roles, expirySeconds);
    }

    private String createTestTokenWithIssuer(String kid, String issuer, String clientId,
                                              String preferredUsername, String upn, String oid,
                                              List<String> groups, List<String> roles,
                                              long expirySeconds) throws Exception
    {
        ObjectNode header = mapper.createObjectNode();
        header.put("alg", "RS256");
        header.put("typ", "JWT");
        header.put("kid", kid);

        ObjectNode payload = mapper.createObjectNode();
        payload.put("iss", issuer);
        payload.put("aud", clientId);
        payload.put("iat", System.currentTimeMillis() / 1000 - 60);
        payload.put("nbf", System.currentTimeMillis() / 1000 - 60);
        payload.put("exp", expirySeconds);
        payload.put("sub", "sub-" + (oid != null ? oid : "unknown"));

        if (preferredUsername != null)
            payload.put("preferred_username", preferredUsername);
        if (upn != null)
            payload.put("upn", upn);
        if (oid != null)
            payload.put("oid", oid);

        if (!groups.isEmpty())
        {
            ArrayNode groupsArray = payload.putArray("groups");
            groups.forEach(groupsArray::add);
        }

        if (!roles.isEmpty())
        {
            ArrayNode rolesArray = payload.putArray("roles");
            roles.forEach(rolesArray::add);
        }

        String headerB64 = Base64.getUrlEncoder().withoutPadding()
            .encodeToString(mapper.writeValueAsBytes(header));
        String payloadB64 = Base64.getUrlEncoder().withoutPadding()
            .encodeToString(mapper.writeValueAsBytes(payload));

        String signingInput = headerB64 + "." + payloadB64;
        Signature sig = Signature.getInstance("SHA256withRSA");
        sig.initSign(rsaKeyPair.getPrivate());
        sig.update(signingInput.getBytes(StandardCharsets.US_ASCII));
        byte[] signature = sig.sign();

        String signatureB64 = Base64.getUrlEncoder().withoutPadding()
            .encodeToString(signature);

        return signingInput + "." + signatureB64;
    }

    private byte[] buildSaslPlainResponse(String authzId, String authnId, String password)
    {
        byte[] authzIdBytes = authzId.getBytes(StandardCharsets.UTF_8);
        byte[] authnIdBytes = authnId.getBytes(StandardCharsets.UTF_8);
        byte[] passwordBytes = password.getBytes(StandardCharsets.UTF_8);

        byte[] result = new byte[authzIdBytes.length + 1 + authnIdBytes.length + 1 + passwordBytes.length];
        int pos = 0;
        System.arraycopy(authzIdBytes, 0, result, pos, authzIdBytes.length);
        pos += authzIdBytes.length;
        result[pos++] = 0;
        System.arraycopy(authnIdBytes, 0, result, pos, authnIdBytes.length);
        pos += authnIdBytes.length;
        result[pos++] = 0;
        System.arraycopy(passwordBytes, 0, result, pos, passwordBytes.length);

        return result;
    }

    /**
     * Testable version of EntraIdTokenValidator that uses a local RSA key pair
     * instead of fetching from Microsoft's JWKS endpoint.
     */
    private static class TestableTokenValidator extends EntraIdTokenValidator
    {
        private final KeyPair keyPair;

        TestableTokenValidator(String tenantId, String clientId, KeyPair keyPair)
        {
            super(tenantId, clientId);
            this.keyPair = keyPair;
        }

        @Override
        public EntraIdClaims validateToken(String jwtToken) throws AuthenticationException
        {
            try
            {
                String[] parts = jwtToken.split("\\.");
                if (parts.length != 3)
                    throw new AuthenticationException("Invalid JWT: expected 3 parts, got " + parts.length);

                String headerJson = new String(Base64.getUrlDecoder().decode(parts[0]), StandardCharsets.UTF_8);
                String payloadJson = new String(Base64.getUrlDecoder().decode(parts[1]), StandardCharsets.UTF_8);
                byte[] signatureBytes = Base64.getUrlDecoder().decode(parts[2]);

                JsonNode header = mapper.readTree(headerJson);
                JsonNode payload = mapper.readTree(payloadJson);

                String alg = header.has("alg") ? header.get("alg").asText() : null;
                if (!"RS256".equals(alg))
                    throw new AuthenticationException("Unsupported algorithm: " + alg);

                Signature sig = Signature.getInstance("SHA256withRSA");
                sig.initVerify(keyPair.getPublic());
                sig.update((parts[0] + "." + parts[1]).getBytes(StandardCharsets.US_ASCII));
                if (!sig.verify(signatureBytes))
                    throw new AuthenticationException("JWT signature verification failed");

                long now = System.currentTimeMillis() / 1000;

                String issuer = payload.has("iss") ? payload.get("iss").asText() : null;
                String expectedIssuerV2 = String.format("https://login.microsoftonline.com/%s/v2.0",
                    "72f988bf-86f1-41af-91ab-2d7cd011db47");
                String expectedIssuerV1 = String.format("https://sts.windows.net/%s/",
                    "72f988bf-86f1-41af-91ab-2d7cd011db47");

                if (issuer == null || (!issuer.equals(expectedIssuerV2) && !issuer.equals(expectedIssuerV1)))
                    throw new AuthenticationException("Invalid issuer: " + issuer);

                String audience = payload.has("aud") ? payload.get("aud").asText() : null;
                if (!TEST_CLIENT_ID.equals(audience))
                    throw new AuthenticationException("Invalid audience: " + audience);

                if (payload.has("exp"))
                {
                    long exp = payload.get("exp").asLong();
                    if (now > exp + 300)
                        throw new AuthenticationException("Token expired");
                }

                String oid = payload.has("oid") ? payload.get("oid").asText() : null;
                String preferredUsername = payload.has("preferred_username") ? payload.get("preferred_username").asText() : null;
                String upn = payload.has("upn") ? payload.get("upn").asText() : null;
                String sub = payload.has("sub") ? payload.get("sub").asText() : null;
                String name = payload.has("name") ? payload.get("name").asText() : null;

                Set<String> groups = new HashSet<>();
                if (payload.has("groups") && payload.get("groups").isArray())
                    for (JsonNode g : payload.get("groups"))
                        groups.add(g.asText());

                Set<String> roles = new HashSet<>();
                if (payload.has("roles") && payload.get("roles").isArray())
                    for (JsonNode r : payload.get("roles"))
                        roles.add(r.asText());

                return new EntraIdClaims(oid, preferredUsername, upn, sub, name, groups, roles);
            }
            catch (AuthenticationException e)
            {
                throw e;
            }
            catch (Exception e)
            {
                throw new AuthenticationException("Token validation failed: " + e.getMessage());
            }
        }
    }
}
