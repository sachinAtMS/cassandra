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
package com.example.cassandra.auth;

import com.datastax.driver.core.AuthProvider;
import com.datastax.driver.core.Authenticator;
import com.datastax.driver.core.exceptions.AuthenticationException;
import com.microsoft.aad.msal4j.*;

import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.concurrent.CompletableFuture;

/**
 * DataStax Java Driver 3.x AuthProvider for Microsoft Entra ID token-based authentication.
 *
 * <p>This provider acquires a JWT access token from Microsoft Entra ID using MSAL4J
 * and sends it to Apache Cassandra's {@code EntraIdAuthenticator} via the SASL PLAIN mechanism.</p>
 *
 * <h3>Usage with Client Credentials (Service Principal / Managed Identity):</h3>
 * <pre>{@code
 * EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()
 *     .tenantId("your-tenant-id")
 *     .clientId("your-client-id")
 *     .clientSecret("your-client-secret")
 *     .scope("api://your-client-id/.default")
 *     .build();
 *
 * Cluster cluster = Cluster.builder()
 *     .addContactPoint("cassandra-host")
 *     .withAuthProvider(authProvider)
 *     .build();
 * }</pre>
 *
 * <h3>Usage with Username/Password (ROPC flow - for dev/test only):</h3>
 * <pre>{@code
 * EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()
 *     .tenantId("your-tenant-id")
 *     .clientId("your-client-id")
 *     .username("user@contoso.com")
 *     .password("user-password")
 *     .scope("api://your-client-id/.default")
 *     .build();
 * }</pre>
 *
 * <h3>Maven Dependencies:</h3>
 * <pre>{@code
 * <dependency>
 *     <groupId>com.datastax.cassandra</groupId>
 *     <artifactId>cassandra-driver-core</artifactId>
 *     <version>3.11.5</version>
 * </dependency>
 * <dependency>
 *     <groupId>com.microsoft.azure</groupId>
 *     <artifactId>msal4j</artifactId>
 *     <version>1.14.0</version>
 * </dependency>
 * }</pre>
 *
 * @see <a href="https://learn.microsoft.com/en-us/entra/identity-platform/">Microsoft Entra ID Platform</a>
 */
public class EntraIdAuthProvider implements AuthProvider
{
    private final String tenantId;
    private final String clientId;
    private final String clientSecret;      // For client_credentials flow
    private final String username;           // For ROPC flow
    private final String password;           // For ROPC flow
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

    @Override
    public Authenticator newAuthenticator(InetSocketAddress host, String authenticator)
        throws AuthenticationException
    {
        // The authenticator string is the FQCN of the server-side authenticator
        // We only respond to EntraIdAuthenticator or any authenticator (for flexibility)
        return new EntraIdAuthenticator();
    }

    /**
     * Acquires an access token from Microsoft Entra ID.
     * Supports three flows:
     * 1. Client Credentials (service principal) - when clientSecret is set
     * 2. Resource Owner Password Credentials (ROPC) - when username/password are set
     * 3. Managed Identity - when useManagedIdentity is true
     */
    private String acquireToken()
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
        return result.accessToken();
    }

    private String acquireTokenWithManagedIdentity() throws Exception
    {
        // For Managed Identity, use the ManagedIdentityApplication
        ManagedIdentityApplication miApp = ManagedIdentityApplication.builder(
            ManagedIdentityId.systemAssigned())
            .build();

        ManagedIdentityParameters parameters = ManagedIdentityParameters.builder(scope)
            .build();

        IAuthenticationResult result = miApp.acquireTokenForManagedIdentity(parameters).get();
        return result.accessToken();
    }

    /**
     * SASL PLAIN authenticator that sends the Entra ID JWT token as the password.
     * The SASL PLAIN format is: authzId NUL authnId NUL password
     * where password contains the JWT access token.
     */
    private class EntraIdAuthenticator implements Authenticator
    {
        private static final byte NUL = 0;

        @Override
        public byte[] initialResponse()
        {
            String token = acquireToken();
            // Determine the username to send (informational - server derives identity from JWT)
            String authnId = (username != null && !username.isEmpty()) ? username : "entra-token";

            // SASL PLAIN format: authzId<NUL>authnId<NUL>password
            byte[] authnIdBytes = authnId.getBytes(StandardCharsets.UTF_8);
            byte[] tokenBytes = token.getBytes(StandardCharsets.UTF_8);

            ByteBuffer buffer = ByteBuffer.allocate(1 + authnIdBytes.length + 1 + tokenBytes.length);
            buffer.put(NUL);                 // authzId (empty)
            buffer.put(authnIdBytes);        // authnId (username)
            buffer.put(NUL);                 // separator
            buffer.put(tokenBytes);          // password (JWT token)

            return buffer.array();
        }

        @Override
        public byte[] evaluateChallenge(byte[] challenge)
        {
            // SASL PLAIN has no challenge-response; this should not be called
            return null;
        }

        @Override
        public void onAuthenticationSuccess(byte[] token)
        {
            // Authentication completed successfully
        }
    }

    // -------------------------
    // Builder
    // -------------------------

    public static Builder builder()
    {
        return new Builder();
    }

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

        public Builder tenantId(String tenantId)
        {
            this.tenantId = tenantId;
            return this;
        }

        public Builder clientId(String clientId)
        {
            this.clientId = clientId;
            return this;
        }

        public Builder clientSecret(String clientSecret)
        {
            this.clientSecret = clientSecret;
            return this;
        }

        public Builder username(String username)
        {
            this.username = username;
            return this;
        }

        public Builder password(String password)
        {
            this.password = password;
            return this;
        }

        /**
         * Sets the scope for token acquisition.
         * Default: api://{clientId}/.default
         */
        public Builder scope(String scope)
        {
            this.scope = scope;
            return this;
        }

        /**
         * Sets the Microsoft Entra ID authority URL.
         * Default: https://login.microsoftonline.com/{tenantId}
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

        public EntraIdAuthProvider build()
        {
            if (tenantId == null || tenantId.isEmpty())
                throw new IllegalArgumentException("tenantId is required");
            if (clientId == null || clientId.isEmpty())
                throw new IllegalArgumentException("clientId is required");
            return new EntraIdAuthProvider(this);
        }
    }
}
