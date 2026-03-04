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

import com.datastax.oss.driver.api.core.auth.AuthenticationException;
import com.datastax.oss.driver.api.core.auth.Authenticator;
import com.datastax.oss.driver.api.core.metadata.EndPoint;
import org.junit.Test;

import java.nio.charset.StandardCharsets;

import static org.junit.Assert.*;

/**
 * Unit tests for {@link EntraIdAuthProviderV4}.
 * Tests builder validation and configuration. Network-dependent tests excluded.
 */
public class EntraIdAuthProviderV4Test
{
    private static final String TENANT_ID = "test-tenant-id";
    private static final String CLIENT_ID = "test-client-id";
    private static final String CLIENT_SECRET = "test-client-secret";

    @Test
    public void testBuilderRequiresTenantId()
    {
        try
        {
            EntraIdAuthProviderV4.builder()
                .clientId(CLIENT_ID)
                .clientSecret(CLIENT_SECRET)
                .build();
            fail("Expected NullPointerException for missing tenantId");
        }
        catch (NullPointerException e)
        {
            assertTrue(e.getMessage().contains("tenantId"));
        }
    }

    @Test
    public void testBuilderRequiresClientId()
    {
        try
        {
            EntraIdAuthProviderV4.builder()
                .tenantId(TENANT_ID)
                .clientSecret(CLIENT_SECRET)
                .build();
            fail("Expected NullPointerException for missing clientId");
        }
        catch (NullPointerException e)
        {
            assertTrue(e.getMessage().contains("clientId"));
        }
    }

    @Test
    public void testBuilderWithClientCredentials()
    {
        EntraIdAuthProviderV4 provider = EntraIdAuthProviderV4.builder()
            .tenantId(TENANT_ID)
            .clientId(CLIENT_ID)
            .clientSecret(CLIENT_SECRET)
            .build();

        assertNotNull(provider);
        assertEquals(TENANT_ID, provider.getTenantId());
        assertEquals(CLIENT_ID, provider.getClientId());
        assertNull(provider.getUsername());
    }

    @Test
    public void testBuilderWithManagedIdentity()
    {
        EntraIdAuthProviderV4 provider = EntraIdAuthProviderV4.builder()
            .tenantId(TENANT_ID)
            .clientId(CLIENT_ID)
            .useManagedIdentity(true)
            .build();

        assertNotNull(provider);
    }

    @Test
    public void testNewAuthenticatorReturnsNonNull()
    {
        EntraIdAuthProviderV4 provider = EntraIdAuthProviderV4.builder()
            .tenantId(TENANT_ID)
            .clientId(CLIENT_ID)
            .clientSecret(CLIENT_SECRET)
            .build();

        // EndPoint is an interface; use a simple mock-style approach
        EndPoint mockEndPoint = new EndPoint()
        {
            @Override
            public java.net.InetSocketAddress resolve()
            {
                return new java.net.InetSocketAddress("127.0.0.1", 9042);
            }

            @Override
            public String asMetricPrefix()
            {
                return "127.0.0.1:9042";
            }
        };

        Authenticator auth = provider.newAuthenticator(mockEndPoint,
            "org.apache.cassandra.auth.EntraIdAuthenticator");

        assertNotNull(auth);
    }

    @Test
    public void testNoAuthMethodThrows()
    {
        EntraIdAuthProviderV4 provider = EntraIdAuthProviderV4.builder()
            .tenantId(TENANT_ID)
            .clientId(CLIENT_ID)
            .build();

        try
        {
            provider.acquireToken();
            fail("Expected AuthenticationException for no auth method");
        }
        catch (AuthenticationException e)
        {
            assertTrue(e.getMessage().contains("No authentication method configured"));
        }
    }

    @Test
    public void testCloseDoesNotThrow() throws Exception
    {
        EntraIdAuthProviderV4 provider = EntraIdAuthProviderV4.builder()
            .tenantId(TENANT_ID)
            .clientId(CLIENT_ID)
            .clientSecret(CLIENT_SECRET)
            .build();

        // Should not throw
        provider.close();
    }
}
