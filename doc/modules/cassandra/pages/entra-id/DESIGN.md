# Microsoft Entra ID Authentication & Authorization for Apache Cassandra
## Design Document

| Field              | Value                                                |
|--------------------|------------------------------------------------------|
| **Title**          | Entra ID Authentication & Authorization for Cassandra|
| **Authors**        | Sachin Gupta                                         |
| **Status**         | Draft                                                |
| **Cassandra Version** | 4.1.x                                            |
| **Created**        | 2026-03-03                                           |
| **JIRA**           | TBD                                                  |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Motivation & Goals](#2-motivation--goals)
3. [Architecture Overview](#3-architecture-overview)
4. [Server-Side Components (Cassandra)](#4-server-side-components-cassandra)
5. [Client-Side Components (Drivers)](#5-client-side-components-drivers)
6. [Authentication Flow](#6-authentication-flow)
7. [Authorization Flow](#7-authorization-flow)
8. [Token Validation](#8-token-validation)
9. [Group-to-Role Mapping](#9-group-to-role-mapping)
10. [Configuration Reference](#10-configuration-reference)
11. [Security Considerations](#11-security-considerations)
12. [Backward Compatibility](#12-backward-compatibility)
13. [Performance Considerations](#13-performance-considerations)
14. [Testing Strategy](#14-testing-strategy)
15. [Future Work](#15-future-work)

---

## 1. Executive Summary

This design introduces **Microsoft Entra ID (formerly Azure Active Directory)** as a first-class
authentication and authorization provider for Apache Cassandra. It enables enterprises to
authenticate Cassandra clients using **JWT access tokens** issued by Microsoft Entra ID, replacing
or complementing the existing username/password-based `PasswordAuthenticator`.

The solution consists of:
- **Server-side**: Three new Java classes in Cassandra's `auth` package (`EntraIdAuthenticator`,
  `EntraIdAuthorizer`, `EntraIdTokenValidator`)
- **Client-side**: Auth provider implementations for DataStax Java Driver (3.x and 4.x),
  DataStax C# Driver, Python Driver, and CQLSH
- **Zero external dependencies** on the server side (uses JDK crypto + existing Jackson)
- **MSAL-based** token acquisition on the client side (Microsoft Authentication Library)

---

## 2. Motivation & Goals

### Problem Statement

Apache Cassandra's built-in `PasswordAuthenticator` stores credentials (bcrypt-hashed passwords)
in the `system_auth.roles` table. This approach has limitations for enterprise environments:

1. **No centralized identity management** — Each Cassandra cluster maintains its own user database
2. **No MFA support** — Password-only authentication cannot integrate with multi-factor authentication
3. **Credential rotation burden** — Passwords must be rotated manually across all clients
4. **No group-based access control** — Permissions must be granted individually per user role
5. **No integration with corporate identity providers** — Cannot leverage existing SSO infrastructure

### Goals

| Goal | Description |
|------|-------------|
| G1 | Enable Entra ID JWT-based authentication for Cassandra clients |
| G2 | Support group-based authorization (Entra ID groups → Cassandra role permissions) |
| G3 | Zero new server-side dependencies (JDK + existing Jackson only) |
| G4 | Backward compatible — existing PasswordAuthenticator continues to work |
| G5 | Support multiple client authentication flows (client credentials, ROPC, managed identity, interactive) |
| G6 | Provide ready-to-use client libraries for Java, C#, Python, and CQLSH |

### Non-Goals

- Replacing `PasswordAuthenticator` — it remains fully supported
- Implementing OpenID Connect Discovery on the server — we use Entra ID's well-known JWKS endpoint directly
- Supporting non-Microsoft identity providers (extendable in the future)
- Implementing refresh token flows on the server (clients handle token lifecycle)

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT SIDE                                  │
│                                                                      │
│  ┌──────────────┐     ┌───────────────────┐     ┌────────────────┐  │
│  │  Application  │────▶│  MSAL Library     │────▶│  Entra ID      │  │
│  │  (Java/C#/   │     │  (msal4j /        │     │  (Microsoft    │  │
│  │   Python)    │     │   MSAL.NET /      │     │   Identity     │  │
│  │              │     │   msal-python)    │     │   Platform)    │  │
│  └──────┬───────┘     └───────────────────┘     └───────┬────────┘  │
│         │                                               │            │
│         │  ◀──── JWT Access Token ──────────────────────┘            │
│         │                                                            │
│  ┌──────▼──────────────┐                                            │
│  │  EntraIdAuthProvider │  (Driver-specific AuthProvider)            │
│  │  - acquireToken()   │                                            │
│  │  - SASL PLAIN       │                                            │
│  │    response builder │                                            │
│  └──────┬──────────────┘                                            │
│         │                                                            │
│         │  SASL PLAIN: NUL + username + NUL + JWT_TOKEN              │
└─────────┼────────────────────────────────────────────────────────────┘
          │
          │  TCP / Native Protocol v4/v5 (AUTH_RESPONSE)
          │
┌─────────▼────────────────────────────────────────────────────────────┐
│                         SERVER SIDE (Cassandra)                       │
│                                                                       │
│  ┌────────────────────────┐                                          │
│  │  EntraIdAuthenticator  │  (IAuthenticator implementation)         │
│  │  - SaslNegotiator      │                                          │
│  │  - decodeCredentials() │                                          │
│  │  - claimsCache         │                                          │
│  └───────────┬────────────┘                                          │
│              │                                                        │
│              ▼                                                        │
│  ┌────────────────────────┐     ┌───────────────────────────────┐   │
│  │  EntraIdTokenValidator │────▶│  Microsoft JWKS Endpoint     │   │
│  │  - RS256 verification  │     │  login.microsoftonline.com/  │   │
│  │  - Claims extraction   │     │  {tenant}/discovery/v2.0/keys │   │
│  │  - iss/aud/exp/nbf     │     └───────────────────────────────┘   │
│  │    validation          │                                          │
│  └───────────┬────────────┘                                          │
│              │                                                        │
│              │  EntraIdClaims (oid, upn, groups, roles)               │
│              ▼                                                        │
│  ┌────────────────────────┐                                          │
│  │  EntraIdAuthorizer     │  (extends CassandraAuthorizer)           │
│  │  - Standard role perms │                                          │
│  │  + Group-mapped perms  │                                          │
│  │                        │     ┌─────────────────────────────┐     │
│  │  entra_group_roles ────┼────▶│  system_auth.entra_group_   │     │
│  │  table lookup          │     │  roles (group_id, role)     │     │
│  └────────────────────────┘     └─────────────────────────────┘     │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 4. Server-Side Components (Cassandra)

### 4.1 EntraIdAuthenticator

**File**: `src/java/org/apache/cassandra/auth/EntraIdAuthenticator.java`

Implements Cassandra's `IAuthenticator` interface. Key responsibilities:

| Method | Purpose |
|--------|---------|
| `requireAuthentication()` | Returns `true` — all connections must authenticate |
| `newSaslNegotiator()` | Returns `EntraIdSaslNegotiator` for native protocol clients |
| `legacyAuthenticate()` | Supports JMX clients by accepting `token` or `password` key |
| `validateConfiguration()` | Reads `entra_tenant_id` and `entra_client_id` from system properties or cassandra.yaml |
| `setup()` | Initializes `EntraIdTokenValidator` with tenant/client IDs |

**Inner class: `EntraIdSaslNegotiator`**
- Implements `IAuthenticator.SaslNegotiator`
- Decodes SASL PLAIN format: `authzId<NUL>authnId<NUL>password`
- Extracts JWT from the `password` field
- Delegates to `validateTokenAndAuthenticate()` which:
  1. Validates the JWT via `EntraIdTokenValidator`
  2. Determines the principal name from claims
  3. Caches claims in `claimsCache` (ConcurrentHashMap) for the authorizer
  4. Returns `AuthenticatedUser(principalName)`

**Claims Cache**: A `static ConcurrentHashMap<String, EntraIdClaims>` shared with `EntraIdAuthorizer`.
Updated on each successful authentication. The authorizer reads group memberships from this cache.

### 4.2 EntraIdTokenValidator

**File**: `src/java/org/apache/cassandra/auth/EntraIdTokenValidator.java`

Pure JWT validation engine using only JDK classes and Jackson. No external JWT libraries.

**Validation Steps:**

```
1. Split JWT into header.payload.signature
2. Decode header → verify alg=RS256, extract kid
3. Fetch RSA public key from JWKS cache (by kid)
4. Verify RS256 signature: SHA256withRSA(header.payload, signature, publicKey)
5. Validate claims:
   - iss ∈ {v1 issuer, v2 issuer} for the configured tenant
   - aud == configured client_id
   - exp + clock_skew > now (token not expired)
   - nbf - clock_skew < now (token is active)
6. Extract identity claims → EntraIdClaims
```

**JWKS Key Cache:**
- Keys fetched from `https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys`
- Cached in `ConcurrentHashMap<kid, PublicKey>` with 24-hour TTL
- Thread-safe refresh with double-checked locking
- Only RSA signing keys (`kty=RSA`, `use=sig`) are cached

**EntraIdClaims** (inner class):

| Claim | JWT Field | Description |
|-------|-----------|-------------|
| `objectId` | `oid` | Unique principal ID in Entra ID |
| `preferredUsername` | `preferred_username` | User email (e.g., user@contoso.com) |
| `upn` | `upn` | User Principal Name |
| `subject` | `sub` | Subject claim |
| `name` | `name` | Display name |
| `groups` | `groups` | Set of Entra ID group Object IDs |
| `roles` | `roles` | Set of app role assignments |

**Principal Name Resolution Priority**: `preferred_username > upn > name > oid > sub`

### 4.3 EntraIdAuthorizer

**File**: `src/java/org/apache/cassandra/auth/EntraIdAuthorizer.java`

Extends `CassandraAuthorizer` to add group-based authorization.

**Permission Resolution** (in `authorize(user, resource)`):

```
permissions = {}

if user.isSuper():
    return resource.applicablePermissions()

// Step 1: Standard Cassandra role permissions
permissions += super.authorize(user, resource)   // from role_permissions table

// Step 2: Entra ID group-based permissions
claims = EntraIdAuthenticator.getCachedClaims(user.name)
if claims != null:
    for groupId in claims.groups:
        for roleName in getGroupRoleMappings(groupId):
            permissions += getPermissionsForRole(roleName, resource)
    for appRole in claims.roles:
        for roleName in getGroupRoleMappings(appRole):
            permissions += getPermissionsForRole(roleName, resource)

return permissions
```

**Group-Role Mapping Table:**

```sql
CREATE TABLE IF NOT EXISTS system_auth.entra_group_roles (
    group_id text,        -- Entra ID group Object ID or app role name
    cassandra_role text,  -- Cassandra role name to inherit permissions from
    PRIMARY KEY (group_id, cassandra_role)
);
```

### 4.4 Configuration (cassandra.yaml)

Two new configuration fields in `Config.java`:

```yaml
# Microsoft Entra ID Configuration
entra_tenant_id: YOUR-TENANT-ID
entra_client_id: YOUR-APPLICATION-CLIENT-ID
```

Also configurable via system properties:
```
-Dcassandra.entra.tenant_id=YOUR-TENANT-ID
-Dcassandra.entra.client_id=YOUR-APPLICATION-CLIENT-ID
```

### 4.5 Deployment Options

The server-side components can be deployed in two ways:

#### Option A — Plugin JAR (Recommended)

Drop a pre-built JAR into Cassandra's `lib/` directory. **No Cassandra source modifications required.**

| Artifact | `org.apache.cassandra:cassandra-entra-id-auth:1.0.0` |
|----------|------------------------------------------------------|
| Build | `cd server-plugin && mvn clean package` |
| Output | `server-plugin/target/cassandra-entra-id-auth-1.0.0.jar` |
| Install | Copy JAR to `$CASSANDRA_HOME/lib/` |
| Config | `conf/entra-id.properties` or JVM system properties |

Configuration is read in this order (first value wins):
1. JVM system properties: `-Dcassandra.entra.tenant_id=...` (in `jvm-server.options`)
2. Properties file: `$CASSANDRA_HOME/conf/entra-id.properties`
3. Custom file path: `-Dcassandra.entra.config=/path/to/file`

The plugin JAR uses the same `org.apache.cassandra.auth` package as Cassandra core, so
short class names work in `cassandra.yaml`:

```yaml
authenticator: EntraIdAuthenticator
authorizer: EntraIdAuthorizer
```

**Compatibility:** Compiled with Java 8 source/target and tested against Cassandra 4.1.x.
Zero new runtime dependencies — the plugin uses only JDK crypto and Cassandra's bundled Jackson.

#### Option B — Source Integration

Compile the classes directly into the Cassandra source tree. This adds `entra_tenant_id` and
`entra_client_id` fields to `Config.java`, allowing configuration via `cassandra.yaml` natively.

See the `src/java/org/apache/cassandra/auth/` directory for the integrated versions.

---

## 5. Client-Side Components (Drivers)

### 5.1 Design Pattern (All Drivers)

All client-side auth providers follow the same pattern:

```
1. Application creates EntraIdAuthProvider with credentials config
2. On connection, driver calls AuthProvider.newAuthenticator()
3. Authenticator.initialResponse() is called:
   a. Acquire JWT from Entra ID (via MSAL)
   b. Build SASL PLAIN response: NUL + username + NUL + JWT
   c. Return the byte array
4. Driver sends AUTH_RESPONSE to Cassandra
5. Cassandra's EntraIdAuthenticator validates the JWT
6. AUTH_SUCCESS or error returned
```

### 5.2 Java Driver (3.x and 4.x)

| Artifact | Driver Version | Package |
|----------|---------------|---------|
| `cassandra-entra-id-auth-driver3` | DataStax 3.x | `org.apache.cassandra.auth.entra` |
| `cassandra-entra-id-auth-driver4` | DataStax 4.x (OSS) | `org.apache.cassandra.auth.entra` |

**Distribution**: Maven artifacts with uber JAR (`-all` classifier) via Maven Shade Plugin.
MSAL4J is relocated to `org.apache.cassandra.shaded.msal4j` to avoid classpath conflicts.

**Dependencies**: `msal4j` (Microsoft Authentication Library for Java) — bundled in uber JAR

**Supported Flows:**
- Client Credentials (service principal with client secret)
- Username/Password (ROPC — dev/test only)
- Managed Identity (Azure VMs, App Service, AKS)

### 5.3 C# Driver

| NuGet Package | Namespace |
|--------------|-----------|
| `Cassandra.Auth.EntraId` | `Cassandra.Auth.EntraId` |

**Distribution**: NuGet package targeting `netstandard2.0`, `net6.0`, `net8.0`.

**Dependencies**: `Microsoft.Identity.Client` (MSAL.NET), `Azure.Identity` (optional)

**Supported Flows:**
- Client Credentials
- Username/Password (ROPC)
- Managed Identity
- DefaultAzureCredential (auto-detection)

### 5.4 Python Driver / CQLSH

| pip Package | Module |
|-------------|--------|
| `cassandra-entra-id-auth` | `cassandra_entra_id_auth` |

**Distribution**: pip package with optional `[azure]` and `[all]` extras.

**Dependencies**: `msal` (MSAL Python), `azure-identity` (optional via `[azure]` extra)

**Supported Flows:**
- Client Credentials
- Username/Password (ROPC)
- Managed Identity
- DefaultAzureCredential
- Pre-acquired Token (pass JWT directly)

**CQLSH Integration**: The auth provider ships with Cassandra in `pylib/cqlshlib/entra_id_auth_provider.py`.
CQLSH's `authproviderhandling.py` loads it via the `[auth_provider]` section in `cqlshrc`.
Additionally, `cqlsh.py` is modified to extract the username from non-PlainText auth providers
for prompt display (`user@cqlsh>`), and the `LOGIN` command supports token re-authentication.

```ini
[auth_provider]
module = cqlshlib.entra_id_auth_provider
classname = EntraIdAuthProvider
tenant_id = YOUR-TENANT-ID
client_id = YOUR-CLIENT-ID
client_secret = YOUR-SECRET
```

---

## 6. Authentication Flow

### 6.1 Sequence Diagram

```
  Client App          MSAL Library       Entra ID           Cassandra Server
      │                    │                │                      │
      │  acquire_token()   │                │                      │
      │───────────────────▶│                │                      │
      │                    │  POST /token   │                      │
      │                    │───────────────▶│                      │
      │                    │                │ Validate credentials  │
      │                    │   JWT Token    │                      │
      │                    │◀───────────────│                      │
      │  JWT access token  │                │                      │
      │◀───────────────────│                │                      │
      │                    │                │                      │
      │  STARTUP message   │                │                      │
      │─────────────────────────────────────────────────────────▶│
      │                    │                │                      │
      │  AUTHENTICATE      │                │  (server says: auth  │
      │  (EntraIdAuth...)  │                │   is required)       │
      │◀─────────────────────────────────────────────────────────│
      │                    │                │                      │
      │  AUTH_RESPONSE     │                │                      │
      │  [NUL|username|NUL|JWT]             │                      │
      │─────────────────────────────────────────────────────────▶│
      │                    │                │                      │
      │                    │                │  ┌──────────────────┐│
      │                    │                │  │ Decode SASL PLAIN ││
      │                    │                │  │ Extract JWT       ││
      │                    │                │  │ Verify RS256 sig  ││
      │                    │                │  │ Validate claims   ││
      │                    │                │  │ Cache groups/roles││
      │                    │                │  └──────────────────┘│
      │                    │                │                      │
      │  AUTH_SUCCESS      │                │                      │
      │◀─────────────────────────────────────────────────────────│
      │                    │                │                      │
      │  READY             │                │                      │
      │◀─────────────────────────────────────────────────────────│
```

### 6.2 Token Validation on Server

The server performs the following validation (no round-trip to Entra ID for each auth):

1. **Signature Verification**: The JWT's RS256 signature is verified against Microsoft's public keys
   (cached from the JWKS endpoint). This proves the token was issued by Microsoft.

2. **Issuer Check**: The `iss` claim must match the configured tenant:
   - v2: `https://login.microsoftonline.com/{tenant}/v2.0`
   - v1: `https://sts.windows.net/{tenant}/`

3. **Audience Check**: The `aud` claim must match the configured `client_id`

4. **Expiry Check**: `exp + 5min > now` (5-minute clock skew tolerance)

5. **Not-Before Check**: `nbf - 5min < now`

---

## 7. Authorization Flow

### 7.1 Permission Resolution

```
                     ┌────────────────────┐
                     │  Authenticated User │
                     │  "user@contoso.com" │
                     └─────────┬──────────┘
                               │
                    ┌──────────▼──────────────┐
                    │                          │
          ┌────────▼────────┐      ┌──────────▼──────────┐
          │ Direct Role     │      │ Entra ID Claims     │
          │ Permissions     │      │ Cache Lookup        │
          │                 │      │                     │
          │ system_auth.    │      │ groups: [g1, g2]    │
          │ role_permissions│      │ roles:  [r1]        │
          │                 │      │                     │
          │ user@contoso.com│      └──────────┬──────────┘
          │ → {SELECT, ...} │                 │
          └────────┬────────┘      ┌──────────▼──────────┐
                   │               │ Group-Role Mapping  │
                   │               │                     │
                   │               │ system_auth.        │
                   │               │ entra_group_roles   │
                   │               │                     │
                   │               │ g1 → db_writers     │
                   │               │ g2 → db_readers     │
                   │               │ r1 → db_admins      │
                   │               └──────────┬──────────┘
                   │                          │
                   │               ┌──────────▼──────────┐
                   │               │ Mapped Role Perms   │
                   │               │                     │
                   │               │ db_writers → {INSERT}│
                   │               │ db_readers → {SELECT}│
                   │               │ db_admins  → {ALL}  │
                   │               └──────────┬──────────┘
                   │                          │
                   └────────────┬─────────────┘
                                │
                     ┌──────────▼──────────┐
                     │ UNION of all perms   │
                     │ {SELECT, INSERT, ALL}│
                     └─────────────────────┘
```

### 7.2 Group-Role Mapping Administration

Administrators manage mappings via CQL:

```sql
-- Map Entra ID group to Cassandra role
INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)
VALUES ('a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'db_readers');

-- Map Entra ID app role to Cassandra role
INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)
VALUES ('CassandraAdmin', 'cassandra_superuser');

-- List all mappings
SELECT * FROM system_auth.entra_group_roles;

-- Remove a mapping
DELETE FROM system_auth.entra_group_roles
WHERE group_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
AND cassandra_role = 'db_readers';
```

---

## 8. Token Validation

### 8.1 JWT Structure

An Entra ID access token is a three-part base64url-encoded JWT:

```
HEADER.PAYLOAD.SIGNATURE
```

**Header**:
```json
{
  "typ": "JWT",
  "alg": "RS256",
  "kid": "key-id-from-jwks"
}
```

**Payload** (relevant claims):
```json
{
  "iss": "https://login.microsoftonline.com/{tenant}/v2.0",
  "aud": "api://your-client-id",
  "exp": 1709510400,
  "nbf": 1709506800,
  "oid": "user-object-id-uuid",
  "preferred_username": "user@contoso.com",
  "upn": "user@contoso.com",
  "name": "User Name",
  "groups": ["group-oid-1", "group-oid-2"],
  "roles": ["CassandraReader", "CassandraWriter"]
}
```

### 8.2 JWKS Key Cache

- **Endpoint**: `https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys`
- **Cache TTL**: 24 hours (configurable)
- **Key Types**: RSA signing keys only (`kty=RSA`, `use=sig`)
- **Refresh Strategy**: Lazy refresh — when a `kid` is not found or cache is expired
- **Thread Safety**: Double-checked locking with `synchronized` block

### 8.3 Clock Skew

A 5-minute (`CLOCK_SKEW_SECONDS = 300`) tolerance is applied to both `exp` and `nbf` claims
to account for clock differences between the Entra ID token service and Cassandra nodes.

---

## 9. Group-to-Role Mapping

### 9.1 Concept

Entra ID organizes users into **Security Groups** (identified by Object IDs) and
**App Roles** (identified by role names configured in the App Registration). These are
included as claims in the JWT token.

This feature maps those Entra ID groups/roles to Cassandra roles, enabling centralized
access control through Azure Portal:

| Entra ID Concept | JWT Claim | Example |
|-----------------|-----------|---------|
| Security Group | `groups` | `["a1b2c3d4-..."]` (Object ID) |
| App Role | `roles` | `["CassandraAdmin"]` (role name) |

### 9.2 Table Schema

```sql
CREATE TABLE system_auth.entra_group_roles (
    group_id text,        -- Entra ID group OID or app role name
    cassandra_role text,  -- Name of existing Cassandra role
    PRIMARY KEY (group_id, cassandra_role)
);
```

### 9.3 Cache Behavior

- Group-role mappings are cached in memory (`ConcurrentHashMap`)
- Cache is populated on startup via `refreshGroupRoleMappings()`
- Individual entries are loaded on-demand if not cached
- Cache can be invalidated via `invalidateGroupMapping()` or `invalidateAllGroupMappings()`

---

## 10. Configuration Reference

### 10.1 Server Configuration (cassandra.yaml)

```yaml
# Authentication
authenticator: org.apache.cassandra.auth.EntraIdAuthenticator

# Authorization
authorizer: org.apache.cassandra.auth.EntraIdAuthorizer

# Role Manager (use standard CassandraRoleManager)
role_manager: CassandraRoleManager

# Microsoft Entra ID Settings
entra_tenant_id: YOUR-AZURE-AD-TENANT-ID
entra_client_id: YOUR-APP-REGISTRATION-CLIENT-ID
```

### 10.2 System Properties (JVM options)

```
-Dcassandra.entra.tenant_id=YOUR-TENANT-ID
-Dcassandra.entra.client_id=YOUR-CLIENT-ID
```

System properties take precedence over cassandra.yaml values.

### 10.3 Client Configuration

See the [Connection Examples](./connection-examples.md) document for per-driver configuration.

---

## 11. Security Considerations

### 11.1 Token Security

| Aspect | Mitigation |
|--------|------------|
| Token in transit | Always use TLS (`client_encryption_options`) between clients and Cassandra |
| Token replay | Tokens have short lifetimes (typically 1 hour); `exp` claim is validated |
| Key compromise | JWKS keys rotate; 24-hour cache TTL ensures fresh keys are picked up |
| Token theft | Use short-lived tokens; implement token binding where possible |

### 11.2 Network Requirements

The Cassandra server nodes must be able to reach Microsoft's JWKS endpoint:
- `https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys` (HTTPS/443)
- This is a one-time fetch per 24 hours (cached); not per-authentication

### 11.3 Recommended Production Settings

```yaml
# Enable TLS for client connections
client_encryption_options:
    enabled: true
    keystore: /path/to/keystore.jks
    keystore_password: cassandra

# Enable TLS for inter-node communication
server_encryption_options:
    internode_encryption: all
```

### 11.4 Audit Trail

All authentication attempts are logged:
- `DEBUG`: Successful authentication with principal name, OID, group count, role count
- `WARN`: Failed authentication with error details
- `INFO`: JWKS cache refresh events
- `INFO`: Group-role mapping load events

---

## 12. Backward Compatibility

### 12.1 Compatibility Matrix

| Scenario | Supported | Notes |
|----------|-----------|-------|
| Existing `PasswordAuthenticator` users | Yes | No changes needed; switch is per-cluster |
| Mixed auth (Password + Entra) | No | A cluster uses one authenticator at a time |
| Existing roles/permissions | Yes | `EntraIdAuthorizer` extends `CassandraAuthorizer` |
| Existing `system_auth` schema | Yes | Only adds `entra_group_roles` table |
| Upgrade path | Yes | Just change `authenticator` and `authorizer` in cassandra.yaml |
| Rollback path | Yes | Revert cassandra.yaml; `entra_group_roles` table is harmless |

### 12.2 Migration Path

1. Create Entra ID app registration (see Azure Setup Guide)
2. Create Cassandra roles matching Entra ID principal names
3. Set up group-role mappings in `entra_group_roles`
4. Update `cassandra.yaml` to use `EntraIdAuthenticator` and `EntraIdAuthorizer`
5. Rolling restart the cluster
6. Update client applications to use `EntraIdAuthProvider`

---

## 13. Performance Considerations

### 13.1 Authentication Performance

| Operation | Latency | Frequency |
|-----------|---------|-----------|
| JWKS fetch | ~100-500ms (network) | Once per 24 hours per node |
| JWT signature verification | ~0.5-2ms (CPU) | Per authentication |
| Claims extraction | ~0.1ms | Per authentication |
| Total server-side auth | ~1-3ms | Per new connection |

**Comparison**: `PasswordAuthenticator` performs a bcrypt hash (50-200ms) plus a table lookup.
EntraID auth is significantly faster on the server side since it uses RSA signature verification
instead of bcrypt.

### 13.2 Authorization Performance

| Operation | Latency | Frequency |
|-----------|---------|-----------|
| Standard role_permissions lookup | ~0.5ms (cached) | Per authorization check |
| Group-role mapping lookup | ~0.1ms (cached) | Per group per authorization |
| role_permissions for mapped role | ~0.5ms (cached) | Per mapped role per authorization |

### 13.3 Memory Usage

| Cache | Approximate Size | Notes |
|-------|-----------------|-------|
| JWKS key cache | ~2KB per key × ~5 keys | Negligible |
| Claims cache | ~1KB per user | Grows with active users |
| Group-role mappings | ~100B per mapping | Typically small |

---

## 14. Testing Strategy

### 14.1 Unit Tests

**File**: `test/unit/org/apache/cassandra/auth/EntraIdAuthenticatorTest.java`

15 tests covering:
| Test | Description |
|------|-------------|
| `testValidToken` | Valid JWT with all claims |
| `testPrincipalNamePriority` | Correct claim priority for principal name |
| `testExpiredToken` | Rejects expired tokens |
| `testWrongAudience` | Rejects tokens with wrong audience |
| `testWrongIssuer` | Rejects tokens with wrong issuer |
| `testTamperedToken` | Rejects tokens with modified payload |
| `testWrongSigningKey` | Rejects tokens signed with wrong key |
| `testMalformedToken` | Rejects malformed JWT strings |
| `testGroupExtraction` | Correctly extracts group claims |
| `testRoleExtraction` | Correctly extracts role claims |
| `testSaslPlainDecoding` | Correctly decodes SASL PLAIN format |
| `testMissingTenantId` | Requires tenant_id configuration |
| `testMissingClientId` | Requires client_id configuration |
| `testRequireAuthentication` | Always returns true |
| `testClaimsCaching` | Claims are cached after auth |

**Approach**: Uses `TestableTokenValidator` with local RSA key pair — no network calls needed.

### 14.2 Integration Tests (Recommended)

- Deploy Cassandra with EntraIdAuthenticator
- Acquire real tokens from an Entra ID test tenant
- Verify end-to-end authentication and authorization
- Test group-role mapping with real Entra ID groups

### 14.3 Driver Tests

Each driver auth provider should be tested with:
- Mock MSAL responses (unit tests)
- Real Entra ID tenant (integration tests)
- Connection establishment and query execution

---

## 15. Future Work

| Item | Description | Priority |
|------|-------------|----------|
| Token refresh | Automatic re-authentication when token expires during long sessions | High |
| EntraIdRoleManager | Custom IRoleManager that syncs roles from Entra ID | Medium |
| Multi-tenant support | Accept tokens from multiple tenants | Medium |
| Certificate-based auth | Support X.509 certificate credentials for service principals | Medium |
| nodetool integration | `nodetool entra-group-mappings` for managing mappings | Low |
| Metrics | Expose auth success/failure metrics via JMX | Low |
| Conditional access | Support Entra ID conditional access policies | Low |
| Token binding | Bind tokens to specific client certificates | Low |

---

## Appendix A: File Inventory

### Server-Side (Cassandra)

| File | Type | Lines | Description |
|------|------|-------|-------------|
| `EntraIdAuthenticator.java` | New | ~293 | IAuthenticator implementation |
| `EntraIdTokenValidator.java` | New | ~445 | JWT validation engine |
| `EntraIdAuthorizer.java` | New | ~336 | IAuthorizer with group-based auth |
| `EntraIdAuthenticatorTest.java` | New | ~400 | 15 unit tests |
| `Config.java` | Modified | +2 fields | entra_tenant_id, entra_client_id |
| `cassandra.yaml` | Modified | +30 lines | Config documentation |

### Client-Side (Drivers)

| File | Language | Description |
|------|----------|-------------|
| `EntraIdAuthProvider.java` | Java (Driver 3.x) | DataStax Java Driver 3.x auth provider |
| `EntraIdAuthProviderV4.java` | Java (Driver 4.x) | DataStax Java Driver 4.x auth provider |
| `EntraIdAuthProvider.cs` | C# | DataStax C# Driver auth provider |
| `entra_id_auth_provider.py` | Python | Python Driver / CQLSH auth provider (shipped in `pylib/cqlshlib/`) |

### CQLSH Core Changes

| File | Description |
|------|-------------|
| `bin/cqlsh.py` | Username extraction for non-PlainText auth providers; `LOGIN` token re-auth support |
| `pylib/cqlshlib/entra_id_auth_provider.py` | Shipped Entra ID auth provider module |

### Documentation

| File | Description |
|------|-------------|
| `DESIGN.md` | This document |
| `AZURE-SETUP-GUIDE.md` | Customer Azure setup instructions |
| `DEVELOPER-GUIDE.md` | Developer onboarding documentation |
| `USER-GUIDE.md` | End-user onboarding documentation |
| `CONNECTION-EXAMPLES.md` | Per-language connection examples |
