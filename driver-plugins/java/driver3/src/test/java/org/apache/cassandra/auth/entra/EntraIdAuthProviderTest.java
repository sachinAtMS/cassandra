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

import com.datastax.driver.core.Authenticator;
import com.datastax.driver.core.exceptions.AuthenticationException;
import org.junit.Test;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

import static org.junit.Assert.*;

/**
 * Unit tests for {@link EntraIdAuthProvider}.
 * Tests builder validation, SASL formatting, and configuration.
 * Network-dependent token acquisition is not tested here.
 */
public class EntraIdAuthProviderTest
{
    private static final String TENANT_ID = "test-tenant-id";
    private static final String CLIENT_ID = "test-client-id";
    private static final String CLIENT_SECRET = "test-client-secret";
    private static final String USERNAME = "user@test.com";
    private static final String PASSWORD = "test-password";

    @Test
    public void testBuilderRequiresTenantId()
    {
        try
        {
            EntraIdAuthProvider.builder()
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
            EntraIdAuthProvider.builder()
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
    public void testBuilderRejectsEmptyTenantId()
    {
        try
        {
            EntraIdAuthProvider.builder()
                .tenantId("")
                .clientId(CLIENT_ID)
                .clientSecret(CLIENT_SECRET)
                .build();
            fail("Expected IllegalArgumentException for empty tenantId");
        }
        catch (IllegalArgumentException e)
        {
            assertTrue(e.getMessage().contains("tenantId"));
        }
    }

    @Test
    public void testBuilderRejectsEmptyClientId()
    {
        try
        {
            EntraIdAuthProvider.builder()
                .tenantId(TENANT_ID)
                .clientId("")
                .clientSecret(CLIENT_SECRET)
                .build();
            fail("Expected IllegalArgumentException for empty clientId");
        }
        catch (IllegalArgumentException e)
        {
            assertTrue(e.getMessage().contains("clientId"));
        }
    }

    @Test
    public void testBuilderWithClientCredentials()
    {
        EntraIdAuthProvider provider = EntraIdAuthProvider.builder()
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
    public void testBuilderWithUsernamePassword()
    {
        EntraIdAuthProvider provider = EntraIdAuthProvider.builder()
            .tenantId(TENANT_ID)
            .clientId(CLIENT_ID)
            .username(USERNAME)
            .password(PASSWORD)
            .build();

        assertNotNull(provider);
        assertEquals(USERNAME, provider.getUsername());
    }

    @Test
    public void testBuilderWithCustomScope()
    {
        String customScope = "https://custom.scope/.default";
        EntraIdAuthProvider provider = EntraIdAuthProvider.builder()
            .tenantId(TENANT_ID)
            .clientId(CLIENT_ID)
            .clientSecret(CLIENT_SECRET)
            .scope(customScope)
            .build();

        assertNotNull(provider);
    }

    @Test
    public void testBuilderWithCustomAuthority()
    {
        String customAuthority = "https://login.microsoftonline.com/common";
        EntraIdAuthProvider provider = EntraIdAuthProvider.builder()
            .tenantId(TENANT_ID)
            .clientId(CLIENT_ID)
            .clientSecret(CLIENT_SECRET)
            .authority(customAuthority)
            .build();

        assertNotNull(provider);
    }

    @Test
    public void testBuilderWithManagedIdentity()
    {
        EntraIdAuthProvider provider = EntraIdAuthProvider.builder()
            .tenantId(TENANT_ID)
            .clientId(CLIENT_ID)
            .useManagedIdentity(true)
            .build();

        assertNotNull(provider);
    }

    @Test
    public void testNewAuthenticatorReturnsNonNull()
    {
        // This test verifies the newAuthenticator method doesn't throw
        // Actual token acquisition requires network so we test the structure only
        EntraIdAuthProvider provider = EntraIdAuthProvider.builder()
            .tenantId(TENANT_ID)
            .clientId(CLIENT_ID)
            .clientSecret(CLIENT_SECRET)
            .build();

        InetSocketAddress host = new InetSocketAddress("127.0.0.1", 9042);
        Authenticator auth = provider.newAuthenticator(host,
            "org.apache.cassandra.auth.EntraIdAuthenticator");

        assertNotNull(auth);
    }

    @Test
    public void testNoAuthMethodThrows()
    {
        // Build a provider with no auth method configured (no secret, no user/pass, no MI)
        EntraIdAuthProvider provider = EntraIdAuthProvider.builder()
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
}
