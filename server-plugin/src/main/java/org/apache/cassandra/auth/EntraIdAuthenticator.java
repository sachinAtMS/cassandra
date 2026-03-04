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

import java.io.FileInputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

import com.google.common.collect.ImmutableSet;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.apache.cassandra.exceptions.AuthenticationException;
import org.apache.cassandra.exceptions.ConfigurationException;
import org.apache.cassandra.schema.SchemaConstants;

/**
 * EntraIdAuthenticator is an IAuthenticator implementation that authenticates
 * users using Microsoft Entra ID (Azure Active Directory) JWT access tokens.
 *
 * <p>This is a <b>drop-in plugin</b> — place the JAR in Cassandra's {@code lib/}
 * directory and configure {@code cassandra.yaml} to use it. No modifications to
 * Cassandra source code are required.</p>
 *
 * <p>Instead of username/password credentials, clients present a JWT access token
 * obtained from Microsoft Entra ID (via MSAL or any OAuth2/OIDC flow). The
 * authenticator validates the token by:</p>
 * <ol>
 *   <li>Verifying the RS256 signature against Microsoft's JWKS endpoint</li>
 *   <li>Checking issuer, audience, expiry, and not-before claims</li>
 *   <li>Extracting the user's identity (preferred_username, UPN, or OID)</li>
 *   <li>Extracting group memberships and app role assignments</li>
 * </ol>
 *
 * <h3>Configuration in cassandra.yaml:</h3>
 * <pre>
 * authenticator: org.apache.cassandra.auth.EntraIdAuthenticator
 * </pre>
 *
 * <h3>Entra ID Configuration (pick one):</h3>
 *
 * <p><b>Option 1 — JVM system properties</b> (in {@code jvm-server.options}):</p>
 * <pre>
 * -Dcassandra.entra.tenant_id=YOUR-TENANT-ID
 * -Dcassandra.entra.client_id=YOUR-APPLICATION-CLIENT-ID
 * </pre>
 *
 * <p><b>Option 2 — Properties file</b> ({@code conf/entra-id.properties}):</p>
 * <pre>
 * tenant_id=YOUR-TENANT-ID
 * client_id=YOUR-APPLICATION-CLIENT-ID
 * </pre>
 *
 * <p>The properties file path can be overridden with
 * {@code -Dcassandra.entra.config=/path/to/entra-id.properties}.</p>
 *
 * <p>System properties take precedence over the properties file.</p>
 *
 * <h3>Client Authentication:</h3>
 * <p>Clients use SASL PLAIN mechanism where:</p>
 * <ul>
 *   <li>username: the Entra ID principal name (or any value — it's verified from the token)</li>
 *   <li>password: the JWT access token from Entra ID</li>
 * </ul>
 *
 * <h3>Role Mapping:</h3>
 * <p>The authenticated user's Cassandra role name is derived from the token's claims in this priority:</p>
 * <ol>
 *   <li>preferred_username (e.g., user@contoso.com)</li>
 *   <li>upn (User Principal Name)</li>
 *   <li>name (Display name)</li>
 *   <li>oid (Object ID — UUID)</li>
 * </ol>
 *
 * <p>The role must exist in Cassandra (created via {@code CREATE ROLE}) for the
 * user to successfully log in. Group memberships from the token are cached
 * and made available to the EntraIdAuthorizer for group-based authorization.</p>
 *
 * @see EntraIdAuthorizer
 * @see EntraIdTokenValidator
 */
public class EntraIdAuthenticator implements IAuthenticator
{
    private static final Logger logger = LoggerFactory.getLogger(EntraIdAuthenticator.class);

    /** System property keys */
    private static final String PROP_TENANT_ID = "cassandra.entra.tenant_id";
    private static final String PROP_CLIENT_ID = "cassandra.entra.client_id";
    private static final String PROP_CONFIG_FILE = "cassandra.entra.config";

    /** Default config file relative to CASSANDRA_HOME */
    private static final String DEFAULT_CONFIG_FILE = "conf/entra-id.properties";

    static final byte NUL = 0;

    /** Shared cache of username -> EntraID claims (groups, roles) from the last valid token.
     *  The EntraIdAuthorizer reads from this to perform group-based authorization. */
    static final Map<String, EntraIdTokenValidator.EntraIdClaims> claimsCache = new ConcurrentHashMap<>();

    private EntraIdTokenValidator tokenValidator;

    private String tenantId;
    private String clientId;

    public EntraIdAuthenticator()
    {
    }

    /**
     * EntraID authenticator always requires authentication.
     */
    @Override
    public boolean requireAuthentication()
    {
        return true;
    }

    @Override
    public Set<? extends IResource> protectedResources()
    {
        return ImmutableSet.of(DataResource.table(SchemaConstants.AUTH_KEYSPACE_NAME, AuthKeyspace.ROLES));
    }

    @Override
    public void validateConfiguration() throws ConfigurationException
    {
        // 1. Try JVM system properties first
        tenantId = System.getProperty(PROP_TENANT_ID);
        clientId = System.getProperty(PROP_CLIENT_ID);

        // 2. Fall back to properties file
        if (isBlank(tenantId) || isBlank(clientId))
        {
            Properties props = loadPropertiesFile();
            if (props != null)
            {
                if (isBlank(tenantId))
                    tenantId = props.getProperty("tenant_id");
                if (isBlank(clientId))
                    clientId = props.getProperty("client_id");
            }
        }

        // 3. Validate
        if (isBlank(tenantId))
            throw new ConfigurationException(
                "Entra ID tenant_id is required. Set it via:\n"
                + "  (a) JVM property: -D" + PROP_TENANT_ID + "=YOUR-TENANT-ID  (in jvm-server.options)\n"
                + "  (b) Properties file: tenant_id=YOUR-TENANT-ID  (in conf/entra-id.properties)\n"
                + "  (c) Custom file path: -D" + PROP_CONFIG_FILE + "=/path/to/entra-id.properties");

        if (isBlank(clientId))
            throw new ConfigurationException(
                "Entra ID client_id is required. Set it via:\n"
                + "  (a) JVM property: -D" + PROP_CLIENT_ID + "=YOUR-CLIENT-ID  (in jvm-server.options)\n"
                + "  (b) Properties file: client_id=YOUR-CLIENT-ID  (in conf/entra-id.properties)\n"
                + "  (c) Custom file path: -D" + PROP_CONFIG_FILE + "=/path/to/entra-id.properties");
    }

    /**
     * Loads Entra ID configuration from a properties file.
     *
     * <p>Resolution order for the properties file path:</p>
     * <ol>
     *   <li>Value of {@code -Dcassandra.entra.config} system property</li>
     *   <li>{@code $CASSANDRA_HOME/conf/entra-id.properties}</li>
     *   <li>{@code conf/entra-id.properties} (relative to working directory)</li>
     * </ol>
     *
     * @return the loaded Properties, or null if no file is found
     */
    private Properties loadPropertiesFile()
    {
        // Explicit config file path via system property
        String configPath = System.getProperty(PROP_CONFIG_FILE);

        if (configPath == null || configPath.isEmpty())
        {
            // Try CASSANDRA_HOME/conf/entra-id.properties
            String cassandraHome = System.getenv("CASSANDRA_HOME");
            if (cassandraHome != null && !cassandraHome.isEmpty())
            {
                Path candidate = Paths.get(cassandraHome, DEFAULT_CONFIG_FILE);
                if (Files.isReadable(candidate))
                    configPath = candidate.toString();
            }

            // Try relative path as last resort
            if (configPath == null)
            {
                Path candidate = Paths.get(DEFAULT_CONFIG_FILE);
                if (Files.isReadable(candidate))
                    configPath = candidate.toString();
            }
        }

        if (configPath == null)
        {
            logger.debug("No Entra ID properties file found; relying on system properties");
            return null;
        }

        Properties props = new Properties();
        try (FileInputStream fis = new FileInputStream(configPath))
        {
            props.load(fis);
            logger.info("Loaded Entra ID configuration from {}", configPath);
            return props;
        }
        catch (IOException e)
        {
            logger.warn("Failed to load Entra ID properties file {}: {}", configPath, e.getMessage());
            return null;
        }
    }

    @Override
    public void setup()
    {
        tokenValidator = new EntraIdTokenValidator(tenantId, clientId);
        logger.info("EntraID Authenticator initialized — tenant: {}, clientId: {}", tenantId, clientId);
    }

    @Override
    public SaslNegotiator newSaslNegotiator(InetAddress clientAddress)
    {
        return new EntraIdSaslNegotiator();
    }

    /**
     * Legacy authentication method (used by JMX and Thrift).
     * Expects a 'token' or 'password' key containing the JWT access token.
     */
    @Override
    public AuthenticatedUser legacyAuthenticate(Map<String, String> credentials) throws AuthenticationException
    {
        String token = credentials.get("token");
        if (token == null)
            token = credentials.get("password");
        if (token == null)
            throw new AuthenticationException("Required key 'token' (or 'password' containing JWT) is missing");

        return validateTokenAndAuthenticate(token);
    }

    /**
     * Validates the JWT token and returns an AuthenticatedUser.
     * Also caches the user's group/role claims for use by EntraIdAuthorizer.
     */
    private AuthenticatedUser validateTokenAndAuthenticate(String jwtToken) throws AuthenticationException
    {
        EntraIdTokenValidator.EntraIdClaims claims = tokenValidator.validateToken(jwtToken);

        String principalName = claims.getPrincipalName();
        if (principalName == null)
            throw new AuthenticationException("Unable to determine user identity from EntraID token. " +
                                              "Token must contain at least one of: preferred_username, upn, name, oid, or sub");

        // Cache the claims so EntraIdAuthorizer can access group memberships
        claimsCache.put(principalName, claims);

        logger.debug("EntraID authentication successful for principal: {} (oid: {}, groups: {}, roles: {})",
                     principalName, claims.objectId, claims.groups.size(), claims.roles.size());

        return new AuthenticatedUser(principalName);
    }

    /**
     * Returns the cached EntraID claims for a given principal name.
     * Used by EntraIdAuthorizer for group-based authorization.
     */
    public static EntraIdTokenValidator.EntraIdClaims getCachedClaims(String principalName)
    {
        return claimsCache.get(principalName);
    }

    private static boolean isBlank(String s)
    {
        return s == null || s.trim().isEmpty();
    }

    /**
     * SASL negotiator for EntraID token-based authentication.
     *
     * <p>Uses SASL PLAIN mechanism format: {@code authzId<NUL>authnId<NUL>password}</p>
     * <p>The password field must contain the Entra ID JWT access token. The authnId
     * (username) field is optional — the actual identity is derived from the token.</p>
     */
    private class EntraIdSaslNegotiator implements SaslNegotiator
    {
        private boolean complete = false;
        private String jwtToken;

        @Override
        public byte[] evaluateResponse(byte[] clientResponse) throws AuthenticationException
        {
            decodeCredentials(clientResponse);
            complete = true;
            return null;
        }

        @Override
        public boolean isComplete()
        {
            return complete;
        }

        @Override
        public AuthenticatedUser getAuthenticatedUser() throws AuthenticationException
        {
            if (!complete)
                throw new AuthenticationException("SASL negotiation not complete");
            return validateTokenAndAuthenticate(jwtToken);
        }

        /**
         * Decodes SASL PLAIN credentials.
         *
         * SASL PLAIN format: {@code authzId<NUL>authnId<NUL>password}
         * For EntraID authentication, the password field contains the JWT access token.
         * The authnId field is informational — the real identity is in the JWT.
         *
         * @param bytes encoded credentials from the client
         * @throws AuthenticationException if the token is missing or empty
         */
        private void decodeCredentials(byte[] bytes) throws AuthenticationException
        {
            logger.trace("Decoding EntraID credentials from client SASL response");

            byte[] token = null;
            int end = bytes.length;
            int nulCount = 0;

            for (int i = bytes.length - 1; i >= 0; i--)
            {
                if (bytes[i] == NUL)
                {
                    if (nulCount == 0)
                    {
                        // First NUL from the right: everything after is the password/token
                        token = Arrays.copyOfRange(bytes, i + 1, end);
                    }
                    nulCount++;
                    end = i;
                }
            }

            if (token == null || token.length == 0)
                throw new AuthenticationException("EntraID JWT access token must be provided in the password field. " +
                                                  "Use SASL PLAIN with: username=<any>, password=<jwt_token>");

            jwtToken = new String(token, StandardCharsets.UTF_8);
        }
    }
}
