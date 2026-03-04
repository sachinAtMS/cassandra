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

import com.datastax.oss.driver.api.core.auth.AuthProvider;
import com.datastax.oss.driver.api.core.auth.AuthenticationException;
import com.datastax.oss.driver.api.core.auth.Authenticator;
import com.datastax.oss.driver.api.core.metadata.EndPoint;
import com.microsoft.aad.msal4j.*;

import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

/**
 * DataStax Java Driver 4.x AuthProvider for Microsoft Entra ID token-based authentication.
 *
 * <p>This provider acquires a JWT access token from Microsoft Entra ID using MSAL4J
 * and sends it to Apache Cassandra's {@code EntraIdAuthenticator} via the SASL PLAIN mechanism.</p>
 *
 * <h3>Usage with application.conf (driver 4.x config):</h3>
 * <pre>
 * datastax-java-driver {
 *   advanced.auth-provider {
 *     class = com.example.cassandra.auth.EntraIdAuthProviderV4
 *   }
 * }
 * </pre>
 *
 * <h3>Programmatic usage:</h3>
 * <pre>{@code
 * EntraIdAuthProviderV4 authProvider = EntraIdAuthProviderV4.builder()
 *     .tenantId("your-tenant-id")
 *     .clientId("your-client-id")
 *     .clientSecret("your-client-secret")
 *     .build();
 *
 * CqlSession session = CqlSession.builder()
 *     .addContactPoint(new InetSocketAddress("cassandra-host", 9042))
 *     .withAuthProvider(authProvider)
 *     .build();
 * }</pre>
 *
 * <h3>Maven Dependencies:</h3>
 * <pre>{@code
 * <dependency>
 *     <groupId>com.datastax.oss</groupId>
 *     <artifactId>java-driver-core</artifactId>
 *     <version>4.17.0</version>
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
public class EntraIdAuthProviderV4 implements AuthProvider
{
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

    private EntraIdAuthProviderV4(Builder builder)
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
    public Authenticator newAuthenticator(EndPoint endPoint, String serverAuthenticator)
        throws AuthenticationException
    {
        return new EntraIdAuthenticator();
    }

    @Override
    public void onMissingChallenge(EndPoint endPoint) throws AuthenticationException
    {
        // Ignore - not all servers send an initial challenge
    }

    @Override
    public void close() throws Exception
    {
        // Nothing to close
    }

    /**
     * Acquires an access token from Microsoft Entra ID.
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
                throw new AuthenticationException(null,
                    "No authentication method configured. " +
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
            Collections.singleton(scope)).build();

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
            Collections.singleton(scope), username, password.toCharArray()).build();

        IAuthenticationResult result = publicClient.acquireToken(parameters).get();
        return result.accessToken();
    }

    private String acquireTokenWithManagedIdentity() throws Exception
    {
        ManagedIdentityApplication miApp = ManagedIdentityApplication.builder(
            ManagedIdentityId.systemAssigned()).build();

        ManagedIdentityParameters parameters = ManagedIdentityParameters.builder(scope).build();

        IAuthenticationResult result = miApp.acquireTokenForManagedIdentity(parameters).get();
        return result.accessToken();
    }

    /**
     * SASL PLAIN authenticator that sends the Entra ID JWT as the password field.
     */
    private class EntraIdAuthenticator implements Authenticator
    {
        private static final byte NUL = 0;

        @Override
        public CompletionStage<ByteBuffer> initialResponse()
        {
            return CompletableFuture.supplyAsync(() -> {
                String token = acquireToken();
                String authnId = (username != null && !username.isEmpty()) ? username : "entra-token";

                byte[] authnIdBytes = authnId.getBytes(StandardCharsets.UTF_8);
                byte[] tokenBytes = token.getBytes(StandardCharsets.UTF_8);

                ByteBuffer buffer = ByteBuffer.allocate(1 + authnIdBytes.length + 1 + tokenBytes.length);
                buffer.put(NUL);
                buffer.put(authnIdBytes);
                buffer.put(NUL);
                buffer.put(tokenBytes);
                buffer.flip();

                return buffer;
            });
        }

        @Override
        public CompletionStage<ByteBuffer> evaluateChallenge(ByteBuffer challenge)
        {
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<Void> onAuthenticationSuccess(ByteBuffer token)
        {
            return CompletableFuture.completedFuture(null);
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

        public Builder tenantId(String tenantId) { this.tenantId = tenantId; return this; }
        public Builder clientId(String clientId) { this.clientId = clientId; return this; }
        public Builder clientSecret(String clientSecret) { this.clientSecret = clientSecret; return this; }
        public Builder username(String username) { this.username = username; return this; }
        public Builder password(String password) { this.password = password; return this; }
        public Builder scope(String scope) { this.scope = scope; return this; }
        public Builder authority(String authority) { this.authority = authority; return this; }
        public Builder useManagedIdentity(boolean useManagedIdentity) { this.useManagedIdentity = useManagedIdentity; return this; }

        public EntraIdAuthProviderV4 build()
        {
            if (tenantId == null || tenantId.isEmpty())
                throw new IllegalArgumentException("tenantId is required");
            if (clientId == null || clientId.isEmpty())
                throw new IllegalArgumentException("clientId is required");
            return new EntraIdAuthProviderV4(this);
        }
    }
}
