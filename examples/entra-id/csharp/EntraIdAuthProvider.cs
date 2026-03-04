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

using System;
using System.Net;
using System.Text;
using System.Threading.Tasks;
using Cassandra;
using Azure.Identity;
using Microsoft.Identity.Client;

namespace Cassandra.Auth.EntraId
{
    /// <summary>
    /// DataStax C# Driver IAuthProvider implementation for Microsoft Entra ID token-based authentication.
    /// 
    /// This provider acquires a JWT access token from Microsoft Entra ID using MSAL.NET
    /// (Microsoft.Identity.Client) or Azure.Identity and sends it to Apache Cassandra's
    /// EntraIdAuthenticator via the SASL PLAIN mechanism.
    /// 
    /// <example>
    /// Usage with Client Credentials (Service Principal):
    /// <code>
    /// var authProvider = new EntraIdAuthProvider(
    ///     tenantId: "your-tenant-id",
    ///     clientId: "your-client-id",
    ///     clientSecret: "your-client-secret"
    /// );
    /// 
    /// var cluster = Cluster.Builder()
    ///     .AddContactPoint("cassandra-host")
    ///     .WithAuthProvider(authProvider)
    ///     .Build();
    /// </code>
    /// </example>
    /// 
    /// <example>
    /// Usage with DefaultAzureCredential (recommended for Azure-hosted apps):
    /// <code>
    /// var authProvider = EntraIdAuthProvider.WithDefaultCredential(
    ///     tenantId: "your-tenant-id",
    ///     clientId: "your-client-id"
    /// );
    /// </code>
    /// </example>
    /// 
    /// NuGet Dependencies:
    /// - CassandraCSharpDriver (>= 3.19.0)
    /// - Microsoft.Identity.Client (>= 4.56.0)
    /// - Azure.Identity (>= 1.10.0)  [optional, for DefaultAzureCredential]
    /// </summary>
    public class EntraIdAuthProvider : IAuthProvider
    {
        private readonly string _tenantId;
        private readonly string _clientId;
        private readonly string _clientSecret;
        private readonly string _username;
        private readonly string _password;
        private readonly string _scope;
        private readonly string _authority;
        private readonly bool _useManagedIdentity;
        private readonly bool _useDefaultCredential;

        private IConfidentialClientApplication _confidentialClient;
        private IPublicClientApplication _publicClient;
        private readonly object _lock = new object();

        /// <summary>
        /// Creates an EntraIdAuthProvider with client credentials (service principal) flow.
        /// </summary>
        /// <param name="tenantId">Microsoft Entra ID tenant ID (directory ID)</param>
        /// <param name="clientId">Application (client) ID registered in Entra ID</param>
        /// <param name="clientSecret">Client secret for the application</param>
        /// <param name="scope">OAuth2 scope. Default: api://{clientId}/.default</param>
        public EntraIdAuthProvider(string tenantId, string clientId, string clientSecret, string scope = null)
        {
            _tenantId = tenantId ?? throw new ArgumentNullException(nameof(tenantId));
            _clientId = clientId ?? throw new ArgumentNullException(nameof(clientId));
            _clientSecret = clientSecret ?? throw new ArgumentNullException(nameof(clientSecret));
            _scope = scope ?? $"api://{clientId}/.default";
            _authority = $"https://login.microsoftonline.com/{tenantId}";
        }

        /// <summary>
        /// Creates an EntraIdAuthProvider with username/password (ROPC) flow.
        /// WARNING: ROPC is not recommended for production. Use client credentials or managed identity.
        /// </summary>
        public EntraIdAuthProvider(string tenantId, string clientId, string username, string password,
                                   string scope = null, bool isRopc = true)
        {
            _tenantId = tenantId ?? throw new ArgumentNullException(nameof(tenantId));
            _clientId = clientId ?? throw new ArgumentNullException(nameof(clientId));
            _username = username ?? throw new ArgumentNullException(nameof(username));
            _password = password ?? throw new ArgumentNullException(nameof(password));
            _scope = scope ?? $"api://{clientId}/.default";
            _authority = $"https://login.microsoftonline.com/{tenantId}";
        }

        /// <summary>
        /// Private constructor for managed identity / default credential flows.
        /// </summary>
        private EntraIdAuthProvider(string tenantId, string clientId, bool useManagedIdentity,
                                    bool useDefaultCredential, string scope)
        {
            _tenantId = tenantId;
            _clientId = clientId;
            _scope = scope ?? $"api://{clientId}/.default";
            _authority = $"https://login.microsoftonline.com/{tenantId}";
            _useManagedIdentity = useManagedIdentity;
            _useDefaultCredential = useDefaultCredential;
        }

        /// <summary>
        /// Creates an EntraIdAuthProvider using Azure Managed Identity.
        /// Use when running on Azure VMs, App Service, AKS, etc.
        /// </summary>
        public static EntraIdAuthProvider WithManagedIdentity(string tenantId, string clientId, string scope = null)
        {
            return new EntraIdAuthProvider(tenantId, clientId,
                useManagedIdentity: true, useDefaultCredential: false, scope: scope);
        }

        /// <summary>
        /// Creates an EntraIdAuthProvider using DefaultAzureCredential.
        /// This automatically tries multiple credential types (environment, managed identity,
        /// VS Code, Azure CLI, etc.) - recommended for Azure-hosted applications.
        /// </summary>
        public static EntraIdAuthProvider WithDefaultCredential(string tenantId, string clientId, string scope = null)
        {
            return new EntraIdAuthProvider(tenantId, clientId,
                useManagedIdentity: false, useDefaultCredential: true, scope: scope);
        }

        /// <summary>
        /// Creates a new authenticator for each connection.
        /// </summary>
        public IAuthenticator NewAuthenticator(IPEndPoint host)
        {
            return new EntraIdAuthenticator(this);
        }

        /// <summary>
        /// Acquires a JWT access token from Microsoft Entra ID.
        /// </summary>
        internal string AcquireToken()
        {
            if (_useDefaultCredential)
            {
                return AcquireTokenWithDefaultCredential();
            }
            else if (_useManagedIdentity)
            {
                return AcquireTokenWithManagedIdentity();
            }
            else if (!string.IsNullOrEmpty(_clientSecret))
            {
                return AcquireTokenWithClientCredentials();
            }
            else if (!string.IsNullOrEmpty(_username))
            {
                return AcquireTokenWithUsernamePassword();
            }
            else
            {
                throw new AuthenticationException("No authentication method configured.");
            }
        }

        private string AcquireTokenWithClientCredentials()
        {
            if (_confidentialClient == null)
            {
                lock (_lock)
                {
                    if (_confidentialClient == null)
                    {
                        _confidentialClient = ConfidentialClientApplicationBuilder.Create(_clientId)
                            .WithClientSecret(_clientSecret)
                            .WithAuthority(new Uri(_authority))
                            .Build();
                    }
                }
            }

            var result = _confidentialClient.AcquireTokenForClient(new[] { _scope })
                .ExecuteAsync().GetAwaiter().GetResult();
            return result.AccessToken;
        }

        private string AcquireTokenWithUsernamePassword()
        {
            if (_publicClient == null)
            {
                lock (_lock)
                {
                    if (_publicClient == null)
                    {
                        _publicClient = PublicClientApplicationBuilder.Create(_clientId)
                            .WithAuthority(new Uri(_authority))
                            .Build();
                    }
                }
            }

            var result = _publicClient.AcquireTokenByUsernamePassword(new[] { _scope }, _username, _password)
                .ExecuteAsync().GetAwaiter().GetResult();
            return result.AccessToken;
        }

        private string AcquireTokenWithManagedIdentity()
        {
            var miApp = ManagedIdentityApplicationBuilder
                .Create(ManagedIdentityId.SystemAssigned)
                .Build();

            var result = miApp.AcquireTokenForManagedIdentity(_scope)
                .ExecuteAsync().GetAwaiter().GetResult();
            return result.AccessToken;
        }

        private string AcquireTokenWithDefaultCredential()
        {
            // Uses Azure.Identity DefaultAzureCredential
            var credential = new DefaultAzureCredential(new DefaultAzureCredentialOptions
            {
                TenantId = _tenantId
            });

            var tokenRequestContext = new Azure.Core.TokenRequestContext(new[] { _scope });
            var token = credential.GetToken(tokenRequestContext);
            return token.Token;
        }

        /// <summary>
        /// Internal authenticator that handles SASL PLAIN negotiation with Entra ID JWT tokens.
        /// </summary>
        private class EntraIdAuthenticator : IAuthenticator
        {
            private readonly EntraIdAuthProvider _provider;

            public EntraIdAuthenticator(EntraIdAuthProvider provider)
            {
                _provider = provider;
            }

            /// <summary>
            /// Returns the initial SASL PLAIN response containing the JWT token.
            /// Format: authzId NUL authnId NUL password(JWT)
            /// </summary>
            public byte[] InitialResponse()
            {
                string token = _provider.AcquireToken();
                string authnId = !string.IsNullOrEmpty(_provider._username)
                    ? _provider._username
                    : "entra-token";

                byte[] authnIdBytes = Encoding.UTF8.GetBytes(authnId);
                byte[] tokenBytes = Encoding.UTF8.GetBytes(token);

                byte[] response = new byte[1 + authnIdBytes.Length + 1 + tokenBytes.Length];
                // authzId (empty) NUL
                response[0] = 0;
                // authnId
                Buffer.BlockCopy(authnIdBytes, 0, response, 1, authnIdBytes.Length);
                // NUL separator
                response[1 + authnIdBytes.Length] = 0;
                // password (JWT token)
                Buffer.BlockCopy(tokenBytes, 0, response, 2 + authnIdBytes.Length, tokenBytes.Length);

                return response;
            }

            public byte[] EvaluateChallenge(byte[] challenge)
            {
                // SASL PLAIN has no challenge-response
                return null;
            }
        }
    }
}
