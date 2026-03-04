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

import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

import com.google.common.collect.ImmutableSet;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.exceptions.AuthenticationException;
import org.apache.cassandra.exceptions.ConfigurationException;
import org.apache.cassandra.schema.SchemaConstants;

/**
 * EntraIdAuthenticator is an IAuthenticator implementation that authenticates
 * users using Microsoft Entra ID (Azure Active Directory) JWT access tokens.
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
 * entra_tenant_id: YOUR-TENANT-ID
 * entra_client_id: YOUR-APPLICATION-CLIENT-ID
 * </pre>
 *
 * <h3>Client Authentication:</h3>
 * <p>Clients use SASL PLAIN mechanism where:</p>
 * <ul>
 *   <li>username: the Entra ID principal name (or any value -- it's verified from the token)</li>
 *   <li>password: the JWT access token from Entra ID</li>
 * </ul>
 *
 * <h3>Role Mapping:</h3>
 * <p>The authenticated user's Cassandra role name is derived from the token's claims in this priority:</p>
 * <ol>
 *   <li>preferred_username (e.g., user@contoso.com)</li>
 *   <li>upn (User Principal Name)</li>
 *   <li>name (Display name)</li>
 *   <li>oid (Object ID - UUID)</li>
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
        tenantId = System.getProperty("cassandra.entra.tenant_id");
        clientId = System.getProperty("cassandra.entra.client_id");

        // Fall back to cassandra.yaml config if system properties are not set
        if (tenantId == null || tenantId.isEmpty())
        {
            try
            {
                String yamlVal = DatabaseDescriptor.getRawConfig().entra_tenant_id;
                if (yamlVal != null && !yamlVal.isEmpty())
                    tenantId = yamlVal;
            }
            catch (Exception e)
            {
                // Config not available (e.g. in tests)
            }
        }

        if (clientId == null || clientId.isEmpty())
        {
            try
            {
                String yamlVal = DatabaseDescriptor.getRawConfig().entra_client_id;
                if (yamlVal != null && !yamlVal.isEmpty())
                    clientId = yamlVal;
            }
            catch (Exception e)
            {
                // Config not available (e.g. in tests)
            }
        }

        if (tenantId == null || tenantId.isEmpty())
            throw new ConfigurationException("entra_tenant_id must be configured in cassandra.yaml " +
                                             "or set via -Dcassandra.entra.tenant_id system property " +
                                             "when using EntraIdAuthenticator");

        if (clientId == null || clientId.isEmpty())
            throw new ConfigurationException("entra_client_id must be configured in cassandra.yaml " +
                                             "or set via -Dcassandra.entra.client_id system property " +
                                             "when using EntraIdAuthenticator");
    }

    @Override
    public void setup()
    {
        tokenValidator = new EntraIdTokenValidator(tenantId, clientId);
        logger.info("EntraID Authenticator initialized - tenant: {}, clientId: {}", tenantId, clientId);
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

    /**
     * SASL negotiator for EntraID token-based authentication.
     *
     * <p>Uses SASL PLAIN mechanism format: {@code authzId<NUL>authnId<NUL>password}</p>
     * <p>The password field must contain the Entra ID JWT access token. The authnId
     * (username) field is optional - the actual identity is derived from the token.</p>
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
         * The authnId field is informational - the real identity is in the JWT.
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
