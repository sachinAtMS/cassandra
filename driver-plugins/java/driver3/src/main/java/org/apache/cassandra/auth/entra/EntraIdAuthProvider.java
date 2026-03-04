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
package org.apache.cassandra.auth.entra;

import com.datastax.driver.core.AuthProvider;
import com.datastax.driver.core.Authenticator;
import com.datastax.driver.core.exceptions.AuthenticationException;
import com.microsoft.aad.msal4j.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.Objects;

/**
 * DataStax Java Driver 3.x {@link AuthProvider} for Microsoft Entra ID token-based authentication.
 *
 * <p>This provider acquires a JWT access token from Microsoft Entra ID using MSAL4J
 * and sends it to Apache Cassandra's {@code EntraIdAuthenticator} via the SASL PLAIN mechanism.</p>
 *
 * <h3>Quick Start - Client Credentials (Service Principal):</h3>
 * <pre>{@code
 * EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()
 *     .tenantId("your-tenant-id")
 *     .clientId("your-client-id")
 *     .clientSecret("your-client-secret")
 *     .build();
 *
 * Cluster cluster = Cluster.builder()
 *     .addContactPoint("cassandra-host")
 *     .withAuthProvider(authProvider)
 *     .build();
 * }</pre>
 *
 * <h3>Username/Password (ROPC - dev/test only):</h3>
 * <pre>{@code
 * EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()
 *     .tenantId("your-tenant-id")
 *     .clientId("your-client-id")
 *     .username("user@contoso.com")
 *     .password("user-password")
 *     .build();
 * }</pre>
 *
 * <h3>Managed Identity (Azure-hosted apps):</h3>
 * <pre>{@code
 * EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()
 *     .tenantId("your-tenant-id")
 *     .clientId("your-client-id")
 *     .useManagedIdentity(true)
 *     .build();
 * }</pre>
 *
 * <h3>Maven Dependency:</h3>
 * <pre>{@code
 * <dependency>
 *     <groupId>org.apache.cassandra</groupId>
 *     <artifactId>cassandra-entra-id-auth-driver3</artifactId>
 *     <version>1.0.0</version>
 * </dependency>
 * }</pre>
 *
 * @see <a href="https://learn.microsoft.com/en-us/entra/identity-platform/">Microsoft Entra ID Platform</a>
 * @see <a href="https://github.com/AzureAD/microsoft-authentication-library-for-java">MSAL4J</a>
 */
public class EntraIdAuthProvider implements AuthProvider
{
    private static final Logger logger = LoggerFactory.getLogger(EntraIdAuthProvider.class);

    private final String tenantId;
    private final String clientId;
    private final String clientSecret;
    private final String username;
    private final String password;
    private final String scope;
    private final String authority;
    private final boolean useManagedIdentity;

    private volatile IConfidentialClientApplication confidentialClient;
    private volatile IPublicClientApplication publicClient;

    private EntraIdAuthProvider(Builder builder)
    {
        this.tenantId = builder.tenantId;
        this.clientId = builder.clientId;
        this.clientSecret = builder.clientSecret;
        this.username = builder.username;
        this.password = builder.password;
        this.scope = builder.scope != null ? builder.scope : "api://" + clientId + "/.default";
        this.authority = builder.authority != null
            ? builder.authority
            : "https://login.microsoftonline.com/" + tenantId;
        this.useManagedIdentity = builder.useManagedIdentity;
    }

    /**
     * Returns the username used for authentication, if available.
     * Useful for display purposes (e.g., CQLSH prompt).
     *
     * @return the configured username, or {@code null} if using service principal or managed identity
     */
    public String getUsername()
    {
        return username;
    }

    /**
     * Returns the configured tenant ID.
     *
     * @return the Microsoft Entra ID tenant ID
     */
    public String getTenantId()
    {
        return tenantId;
    }

    /**
     * Returns the configured client ID.
     *
     * @return the application (client) ID
     */
    public String getClientId()
    {
        return clientId;
    }

    @Override
    public Authenticator newAuthenticator(InetSocketAddress host, String authenticator)
        throws AuthenticationException
    {
        logger.debug("Creating Entra ID authenticator for host {} (server authenticator: {})",
                     host, authenticator);
        return new EntraIdSaslAuthenticator();
    }

    /**
     * Acquires an access token from Microsoft Entra ID.
     *
     * <p>Supports three authentication flows:</p>
     * <ol>
     *   <li><b>Managed Identity</b> - when {@code useManagedIdentity} is {@code true}</li>
     *   <li><b>Client Credentials</b> (service principal) - when {@code clientSecret} is set</li>
     *   <li><b>ROPC</b> (username/password) - when {@code username} and {@code password} are set</li>
     * </ol>
     *
     * @return the JWT access token string
     * @throws AuthenticationException if no auth method is configured or token acquisition fails
     */
    String acquireToken()
    {
        try
        {
            if (useManagedIdentity)
            {
                return acquireTokenWithManagedIdentity();
            }
            else if (clientSecret != null && !clientSecret.isEmpty())
            {
                return acquireTokenWithClientCredentials();
            }
            else if (username != null && !username.isEmpty())
            {
                return acquireTokenWithUsernamePassword();
            }
            else
            {
                throw new AuthenticationException(
                    null, "No authentication method configured. " +
                    "Provide clientSecret (service principal), username/password (ROPC), " +
                    "or enable Managed Identity.");
            }
        }
        catch (AuthenticationException e)
        {
            throw e;
        }
        catch (Exception e)
        {
            throw new AuthenticationException(null,
                "Failed to acquire Entra ID token: " + e.getMessage());
        }
    }

    private String acquireTokenWithClientCredentials() throws Exception
    {
        if (confidentialClient == null)
        {
            synchronized (this)
            {
                if (confidentialClient == null)
                {
                    logger.debug("Initializing confidential client application for tenant {}", tenantId);
                    confidentialClient = ConfidentialClientApplication.builder(clientId,
                            ClientCredentialFactory.createFromSecret(clientSecret))
                        .authority(authority)
                        .build();
                }
            }
        }

        ClientCredentialParameters parameters = ClientCredentialParameters.builder(
            Collections.singleton(scope))
            .build();

        IAuthenticationResult result = confidentialClient.acquireToken(parameters).get();
        logger.debug("Acquired token via client credentials flow (expires: {})", result.expiresOnDate());
        return result.accessToken();
    }

    private String acquireTokenWithUsernamePassword() throws Exception
    {
        if (publicClient == null)
        {
            synchronized (this)
            {
                if (publicClient == null)
                {
                    logger.debug("Initializing public client application for ROPC flow");
                    publicClient = PublicClientApplication.builder(clientId)
                        .authority(authority)
                        .build();
                }
            }
        }

        UserNamePasswordParameters parameters = UserNamePasswordParameters.builder(
            Collections.singleton(scope), username, password.toCharArray())
            .build();

        IAuthenticationResult result = publicClient.acquireToken(parameters).get();
        logger.debug("Acquired token via ROPC flow for user: {} (expires: {})",
                     username, result.expiresOnDate());
        return result.accessToken();
    }

    private String acquireTokenWithManagedIdentity() throws Exception
    {
        logger.debug("Acquiring token via Managed Identity");

        ManagedIdentityApplication miApp = ManagedIdentityApplication.builder(
            ManagedIdentityId.systemAssigned())
            .build();

        ManagedIdentityParameters parameters = ManagedIdentityParameters.builder(scope)
            .build();

        IAuthenticationResult result = miApp.acquireTokenForManagedIdentity(parameters).get();
        logger.debug("Acquired token via Managed Identity (expires: {})", result.expiresOnDate());
        return result.accessToken();
    }

    /**
     * SASL PLAIN authenticator that sends the Entra ID JWT token as the password field.
     *
     * <p>SASL PLAIN format: {@code authzId NUL authnId NUL password}</p>
     * <ul>
     *   <li>{@code authzId} - empty (authorization identity)</li>
     *   <li>{@code authnId} - username or "entra-token" (informational; identity is derived from JWT)</li>
     *   <li>{@code password} - the JWT access token from Entra ID</li>
     * </ul>
     */
    private class EntraIdSaslAuthenticator implements Authenticator
    {
        private static final byte NUL = 0;

        @Override
        public byte[] initialResponse()
        {
            String token = acquireToken();
            String authnId = (username != null && !username.isEmpty()) ? username : "entra-token";

            byte[] authnIdBytes = authnId.getBytes(StandardCharsets.UTF_8);
            byte[] tokenBytes = token.getBytes(StandardCharsets.UTF_8);

            ByteBuffer buffer = ByteBuffer.allocate(1 + authnIdBytes.length + 1 + tokenBytes.length);
            buffer.put(NUL);
            buffer.put(authnIdBytes);
            buffer.put(NUL);
            buffer.put(tokenBytes);

            return buffer.array();
        }

        @Override
        public byte[] evaluateChallenge(byte[] challenge)
        {
            // SASL PLAIN has no challenge-response phase
            return null;
        }

        @Override
        public void onAuthenticationSuccess(byte[] token)
        {
            logger.debug("Entra ID authentication successful");
        }
    }

    // -------------------------------------------------------------------------
    // Builder
    // -------------------------------------------------------------------------

    /**
     * Creates a new {@link Builder} instance.
     *
     * @return a new builder
     */
    public static Builder builder()
    {
        return new Builder();
    }

    /**
     * Builder for constructing {@link EntraIdAuthProvider} instances.
     *
     * <p>At minimum, {@code tenantId} and {@code clientId} are required.
     * Then configure one of the authentication flows:</p>
     * <ul>
     *   <li>{@link #clientSecret(String)} - for service principal / client credentials flow</li>
     *   <li>{@link #username(String)} + {@link #password(String)} - for ROPC flow (dev/test only)</li>
     *   <li>{@link #useManagedIdentity(boolean)} - for Azure Managed Identity</li>
     * </ul>
     */
    public static class Builder
    {
        private String tenantId;
        private String clientId;
        private String clientSecret;
        private String username;
        private String password;
        private String scope;
        private String authority;
        private boolean useManagedIdentity = false;

        /**
         * Sets the Microsoft Entra ID tenant ID (directory ID). <b>Required.</b>
         */
        public Builder tenantId(String tenantId)
        {
            this.tenantId = tenantId;
            return this;
        }

        /**
         * Sets the application (client) ID registered in Microsoft Entra ID. <b>Required.</b>
         */
        public Builder clientId(String clientId)
        {
            this.clientId = clientId;
            return this;
        }

        /**
         * Sets the client secret for client credentials (service principal) flow.
         */
        public Builder clientSecret(String clientSecret)
        {
            this.clientSecret = clientSecret;
            return this;
        }

        /**
         * Sets the username for ROPC (Resource Owner Password Credentials) flow.
         * <b>Not recommended for production.</b> Use client credentials or managed identity instead.
         */
        public Builder username(String username)
        {
            this.username = username;
            return this;
        }

        /**
         * Sets the password for ROPC flow.
         * <b>Not recommended for production.</b>
         */
        public Builder password(String password)
        {
            this.password = password;
            return this;
        }

        /**
         * Sets the OAuth2 scope for token acquisition.
         * Default: {@code api://{clientId}/.default}
         */
        public Builder scope(String scope)
        {
            this.scope = scope;
            return this;
        }

        /**
         * Sets the Microsoft Entra ID authority URL.
         * Default: {@code https://login.microsoftonline.com/{tenantId}}
         */
        public Builder authority(String authority)
        {
            this.authority = authority;
            return this;
        }

        /**
         * Enables Azure Managed Identity authentication.
         * Use when running on Azure VMs, App Service, AKS, etc.
         */
        public Builder useManagedIdentity(boolean useManagedIdentity)
        {
            this.useManagedIdentity = useManagedIdentity;
            return this;
        }

        /**
         * Builds the {@link EntraIdAuthProvider} instance.
         *
         * @return the configured auth provider
         * @throws IllegalArgumentException if required fields (tenantId, clientId) are missing
         */
        public EntraIdAuthProvider build()
        {
            Objects.requireNonNull(tenantId, "tenantId is required");
            Objects.requireNonNull(clientId, "clientId is required");
            if (tenantId.isEmpty())
                throw new IllegalArgumentException("tenantId must not be empty");
            if (clientId.isEmpty())
                throw new IllegalArgumentException("clientId must not be empty");
            return new EntraIdAuthProvider(this);
        }
    }
}
