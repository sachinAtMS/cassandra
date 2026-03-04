# Entra ID Authentication for Apache Cassandra — Developer Guide

This document is for **engineers** who build, maintain, or extend the Entra ID authentication
and authorization feature in Apache Cassandra and its client drivers.

---

## Table of Contents

1. [Architecture Deep Dive](#1-architecture-deep-dive)
2. [Server-Side Implementation Details](#2-server-side-implementation-details)
3. [Client-Side Implementation Details](#3-client-side-implementation-details)
4. [Build & Test](#4-build--test)
5. [Adding a New Driver Implementation](#5-adding-a-new-driver-implementation)
6. [Extending the Feature](#6-extending-the-feature)
7. [Debugging Guide](#7-debugging-guide)
8. [Code Style & Conventions](#8-code-style--conventions)

---

## 1. Architecture Deep Dive

### 1.1 How Cassandra Authentication Works

Cassandra's authentication is a pluggable system built on three interfaces:

```
IAuthenticator       — Authenticates connections (verifies identity)
  └─ SaslNegotiator  — Handles SASL challenge-response per connection
IAuthorizer          — Authorizes operations (checks permissions)
IRoleManager         — Manages roles (create/drop/alter/grant)
```

These are wired in `AuthConfig.applyAuth()` which is called during Cassandra startup:

```java
// AuthConfig.java — simplified
public static void applyAuth() {
    IAuthenticator authenticator = FBUtilities.newAuthenticator();  // from cassandra.yaml
    IAuthorizer authorizer = FBUtilities.newAuthorizer();
    IRoleManager roleManager = FBUtilities.newRoleManager();
    
    authenticator.validateConfiguration();
    authorizer.validateConfiguration();
    roleManager.validateConfiguration();
    
    DatabaseDescriptor.setAuthenticator(authenticator);
    DatabaseDescriptor.setAuthorizer(authorizer);
    DatabaseDescriptor.setRoleManager(roleManager);
}
```

`FBUtilities.newAuthenticator()` supports short names — if the class name doesn't contain
a dot, it prepends `org.apache.cassandra.auth.`. So `EntraIdAuthenticator` in cassandra.yaml
works without the full package name.

### 1.2 Native Protocol Auth Flow

```
Client                          Server
  │                               │
  │  STARTUP                      │
  │──────────────────────────────▶│
  │                               │  Checks requireAuthentication()
  │  AUTHENTICATE                 │  Sends authenticator FQCN
  │◀──────────────────────────────│
  │                               │
  │  AUTH_RESPONSE [SASL data]    │  Creates SaslNegotiator
  │──────────────────────────────▶│  Calls evaluateResponse()
  │                               │
  │  AUTH_SUCCESS                 │  Calls getAuthenticatedUser()
  │◀──────────────────────────────│
```

For SASL PLAIN (which we use), authentication completes in a single round-trip.
The client sends all credentials in the AUTH_RESPONSE message.

### 1.3 SASL PLAIN Wire Format

```
Byte layout: [authzId] NUL [authnId] NUL [password]

For EntraID:
  authzId  = "" (empty)
  authnId  = "user@contoso.com" (informational — actual identity from JWT)
  password = "eyJhbGciOiJSUzI1NiIs..." (JWT access token)

Complete bytes: 0x00 | authnId_bytes | 0x00 | jwt_bytes
```

---

## 2. Server-Side Implementation Details

### 2.1 File Locations

**Source-integrated version** (compiled into Cassandra):
```
src/java/org/apache/cassandra/auth/
├── EntraIdAuthenticator.java      — IAuthenticator implementation
├── EntraIdTokenValidator.java     — JWT validation (no external deps)
├── EntraIdAuthorizer.java         — CassandraAuthorizer + group auth

src/java/org/apache/cassandra/config/
├── Config.java                    — Added entra_tenant_id, entra_client_id

conf/
├── cassandra.yaml                 — Configuration documentation

test/unit/org/apache/cassandra/auth/
├── EntraIdAuthenticatorTest.java  — 15 unit tests
```

**Plugin JAR version** (drop-in, no Cassandra source modification):
```
server-plugin/
├── pom.xml                        — Maven build (Java 8 target, cassandra-all provided)
├── conf/
│   └── entra-id.properties.example — Example config file
├── src/main/java/org/apache/cassandra/auth/
│   ├── EntraIdAuthenticator.java  — Reads config from properties file / system props
│   ├── EntraIdTokenValidator.java — Identical to source version
│   └── EntraIdAuthorizer.java     — Identical to source version
└── src/test/java/org/apache/cassandra/auth/
    └── EntraIdAuthenticatorTest.java — 18 tests (includes properties file tests)
```

### 2.2 EntraIdTokenValidator — JWT Validation Without Dependencies

The design choice to avoid external JWT libraries (nimbus-jose, auth0-java-jwt, etc.) was 
intentional:

**Rationale:**
- Cassandra has strict dependency management (ant-based build, relocated shaded JARs)
- Adding a JWT library cascades into transitive dependencies
- JDK 11+ provides all needed crypto primitives
- Jackson is already a Cassandra dependency

**How it works:**

```
JWT = base64url(header) + "." + base64url(payload) + "." + base64url(signature)

1. Split by "."
2. Decode header JSON → extract "alg" (must be RS256) and "kid"
3. Fetch RSA public key by "kid" from JWKS cache
4. Verify: java.security.Signature.getInstance("SHA256withRSA")
   sig.initVerify(publicKey)
   sig.update( (header + "." + payload).getBytes(US_ASCII) )
   sig.verify(signatureBytes)
5. Decode payload JSON → validate iss, aud, exp, nbf
6. Extract claims → return EntraIdClaims
```

Key JDK classes used:
- `java.security.Signature` — RSA-SHA256 signature verification
- `java.security.KeyFactory` — Build RSA public key from modulus/exponent
- `java.security.spec.RSAPublicKeySpec` — RSA key specification
- `java.math.BigInteger` — For modulus/exponent from base64url
- `java.util.Base64.getUrlDecoder()` — Base64url decoding (no padding)
- `java.net.HttpURLConnection` — JWKS endpoint fetch

Jackson classes used:
- `com.fasterxml.jackson.databind.ObjectMapper` — JSON parsing
- `com.fasterxml.jackson.databind.JsonNode` — JSON tree navigation

### 2.3 Claims Cache Architecture

```
EntraIdAuthenticator                    EntraIdAuthorizer
┌──────────────────────┐                ┌──────────────────────┐
│                      │                │                      │
│  static claimsCache  │◀──── reads ───│  authorize(user, res)│
│  ConcurrentHashMap   │                │                      │
│  <String, Claims>    │                │  getCachedClaims()   │
│                      │                │                      │
│  put(principal,      │                │  claims.groups → ... │
│       claims)        │                │                      │
│  on auth success     │                │                      │
└──────────────────────┘                └──────────────────────┘
```

The claims cache is a `static ConcurrentHashMap` in `EntraIdAuthenticator`. When a user
authenticates successfully, their Entra ID claims (including group memberships and app roles)
are cached. The `EntraIdAuthorizer` reads from this cache to resolve group-based permissions.

**Cache lifetime**: Claims remain until the user re-authenticates with a new token.
This means group changes take effect on the next connection, not immediately.

**Thread safety**: `ConcurrentHashMap` provides thread-safe reads and writes without locking.

### 2.4 EntraIdAuthorizer — Permission Union

The authorizer extends `CassandraAuthorizer` (not replaces it). This means:
- All standard CQL operations work: `GRANT`, `REVOKE`, `LIST ALL PERMISSIONS`
- `system_auth.role_permissions` table is used as-is
- Group-based permissions are **additive** — they add to direct role permissions

```java
// Simplified authorize() logic
Set<Permission> authorize(AuthenticatedUser user, IResource resource) {
    Set<Permission> perms = new EnumSet<>();
    
    // 1. Direct role permissions (from CassandraAuthorizer)
    perms.addAll(super.authorize(user, resource));
    
    // 2. Group-mapped permissions (from Entra ID claims)
    EntraIdClaims claims = EntraIdAuthenticator.getCachedClaims(user.getName());
    if (claims != null) {
        for (String groupId : claims.groups) {
            for (String roleName : lookupGroupRoles(groupId)) {
                perms.addAll(lookupRolePermissions(roleName, resource));
            }
        }
    }
    
    return perms;  // Union of all permission sources
}
```

### 2.5 Error Handling Strategy

| Error | Server Response | Log Level |
|-------|----------------|-----------|
| Malformed JWT | `AuthenticationException` | WARN |
| Invalid signature | `AuthenticationException` | WARN |
| Expired token | `AuthenticationException` | DEBUG |
| Wrong audience | `AuthenticationException` | WARN |
| JWKS fetch failure | `AuthenticationException` | ERROR |
| Missing config | `ConfigurationException` (startup fails) | — |
| Group lookup failure | Silent fallback (empty permissions) | DEBUG |

---

## 3. Client-Side Implementation Details

### 3.1 Token Acquisition Patterns

All client-side auth providers use MSAL to acquire tokens. The three main flows:

**Client Credentials (Service Principal):**
```
POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id={client_id}
&client_secret={client_secret}
&scope=api://{client_id}/.default
```

**Username/Password (ROPC):**
```
POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

grant_type=password
&client_id={client_id}
&username={user}
&password={pass}
&scope=api://{client_id}/.default
```

**Managed Identity:**
```
GET http://169.254.169.254/metadata/identity/oauth2/token
  ?api-version=2018-02-01
  &resource=api://{client_id}
Metadata: true
```

### 3.2 SASL Response Construction

All drivers build the same byte array:

```
byte[] response = new byte[1 + authnId.length + 1 + jwt.length];
response[0] = 0x00;                              // authzId (empty)
System.arraycopy(authnId, 0, response, 1, ...);  // authnId (username)
response[1 + authnId.length] = 0x00;             // NUL separator  
System.arraycopy(jwt, 0, response, ...);          // password (JWT token)
```

### 3.3 Driver-Specific Notes

**Java 3.x** (`com.datastax.driver.core.AuthProvider`):
- `newAuthenticator(InetSocketAddress, String)` — returns `Authenticator`
- `Authenticator.initialResponse()` returns `byte[]`
- Synchronous API

**Java 4.x** (`com.datastax.oss.driver.api.core.auth.AuthProvider`):
- `newAuthenticator(EndPoint, String)` — returns `Authenticator`
- `Authenticator.initialResponse()` returns `CompletionStage<ByteBuffer>`
- Async API (but we use `CompletableFuture.supplyAsync()`)

**C#** (`Cassandra.IAuthProvider`):
- `NewAuthenticator(IPEndPoint)` — returns `IAuthenticator`
- `IAuthenticator.InitialResponse()` returns `byte[]`
- Synchronous API

**Python** (`cassandra.auth.AuthProvider`):
- `new_authenticator(host)` — returns `Authenticator`
- `Authenticator.initial_response()` returns `bytes`
- Synchronous API
- Also used by CQLSH via `[auth_provider]` config in cqlshrc

### 3.4 CQLSH Code Changes

In addition to the auth provider module (`pylib/cqlshlib/entra_id_auth_provider.py`), two
changes were made to `bin/cqlsh.py`:

**Username extraction** (Shell `__init__`):
```python
# Original: only PlainTextAuthProvider
if isinstance(auth_provider, PlainTextAuthProvider):
    self.username = auth_provider.username

# Added: support any auth provider that exposes a username attribute
elif auth_provider is not None and hasattr(auth_provider, 'username') and auth_provider.username:
    self.username = auth_provider.username
```

This ensures the CQLSH prompt shows `user@cqlsh>` when using Entra ID with a username.

**`do_login` command**:
The `LOGIN` command was hardcoded to create `PlainTextAuthProvider`. Updated to:
- When using token auth and `LOGIN` is called without arguments, re-authenticate with the
  current auth provider (acquires a fresh token)
- When using token auth and `LOGIN user pass` is called, fall back to PlainTextAuthProvider
  for backward compatibility
- Standard `LOGIN user [pass]` behavior is unchanged

---

## 4. Build & Test

### 4.1 Building Cassandra

```bash
# Prerequisites: JDK 11, ant
export CASSANDRA_USE_JDK11=true
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64

# Full build
ant jar

# Run EntraID-specific tests
ant test -Dtest.name=EntraIdAuthenticatorTest

# Run all auth tests
ant test -Dtest.name=*Auth*
```

### 4.2 Test Architecture

The unit tests use a `TestableTokenValidator` that overrides the real validator:

```java
class TestableTokenValidator extends EntraIdTokenValidator {
    private final KeyPair localKeyPair;  // RSA key pair generated locally
    
    @Override
    public EntraIdClaims validateToken(String jwt) {
        // Validates using localKeyPair instead of fetching JWKS
        // No network calls needed!
    }
}
```

This approach:
- Generates an RSA key pair in `@BeforeClass`
- Creates signed JWTs using the private key
- Validates using the public key
- No network calls, no Entra ID tenant needed
- Deterministic and fast (~22 seconds for all 15 tests)

### 4.3 Adding New Tests

To add a new test case:

```java
@Test
public void testNewScenario() throws Exception {
    // 1. Build custom claims
    Map<String, Object> claims = new HashMap<>();
    claims.put("oid", "test-oid");
    claims.put("preferred_username", "test@contoso.com");
    // ... add scenario-specific claims

    // 2. Create a signed token
    String token = createTestToken(claims, testKeyPair.getPrivate(), 
                                   TEST_TENANT_ID, TEST_CLIENT_ID, 3600);

    // 3. Validate
    EntraIdTokenValidator.EntraIdClaims result = testValidator.validateToken(token);

    // 4. Assert
    assertEquals("test@contoso.com", result.getPrincipalName());
}
```

### 4.4 Integration Testing

For integration tests with a real Entra ID tenant:

```bash
# Set environment variables
export ENTRA_TENANT_ID=your-real-tenant-id
export ENTRA_CLIENT_ID=your-real-client-id
export ENTRA_CLIENT_SECRET=your-real-secret

# Run integration tests (requires Cassandra running with EntraIdAuthenticator)
ant test -Dtest.name=EntraIdIntegrationTest
```

### 4.5 Building the Server-Side Plugin JAR

The server-side plugin lives in `server-plugin/` and produces a standalone JAR that can be
dropped into any Cassandra 4.1.x node's `lib/` directory.

```bash
cd server-plugin
mvn clean package          # build + test (18 tests)
mvn clean package -DskipTests  # build only
```

**Output:** `server-plugin/target/cassandra-entra-id-auth-1.0.0.jar`

**Key design differences from the source-integrated version:**
- No dependency on `Config.java` field additions (`entra_tenant_id`, `entra_client_id`)
- Configuration read from `conf/entra-id.properties` or JVM system properties
- Same `org.apache.cassandra.auth` package so short names work in `cassandra.yaml`
- Compiled with Java 8 source/target for maximum compatibility
- Zero new runtime dependencies (JDK crypto + Cassandra's bundled Jackson)
- `cassandra-all:4.1.7` declared as `provided` (on the classpath at runtime)

### 4.6 Building Driver Plugins

Pre-built driver auth provider plugins live in `driver-plugins/`. Each produces a
distributable artifact (JAR, NuGet, pip) that customers add to their project.

```
driver-plugins/
├── java/           # Maven multi-module → uber JARs
│   ├── driver3/    #   org.apache.cassandra:cassandra-entra-id-auth-driver3
│   └── driver4/    #   org.apache.cassandra:cassandra-entra-id-auth-driver4
├── csharp/         # .NET solution → NuGet package (Cassandra.Auth.EntraId)
├── python/         # setuptools → pip package (cassandra-entra-id-auth)
├── build-all.sh    # Build all plugins (Linux/macOS)
└── build-all.bat   # Build all plugins (Windows)
```

**Build all plugins at once:**
```bash
cd driver-plugins
./build-all.sh all    # Linux/macOS
build-all.bat all     # Windows
```

**Build individual plugins:**
```bash
# Java (requires JDK 8+ and Maven 3.6+)
cd driver-plugins/java && mvn clean package

# C# (requires .NET SDK 6.0+)
cd driver-plugins/csharp && dotnet pack -c Release

# Python (requires Python 3.7+)
cd driver-plugins/python && pip install build && python -m build
```

**Build outputs:**

| Plugin | Artifact | Location |
|--------|----------|----------|
| Java 3.x | `cassandra-entra-id-auth-driver3-1.0.0-all.jar` | `driver-plugins/java/driver3/target/` |
| Java 4.x | `cassandra-entra-id-auth-driver4-1.0.0-all.jar` | `driver-plugins/java/driver4/target/` |
| C# | `Cassandra.Auth.EntraId.1.0.0.nupkg` | `driver-plugins/csharp/Cassandra.Auth.EntraId/bin/Release/` |
| Python | `cassandra_entra_id_auth-1.0.0.tar.gz` | `driver-plugins/python/dist/` |

The Java uber JARs use Maven Shade Plugin to relocate `com.microsoft.aad.msal4j` into
`org.apache.cassandra.shaded.msal4j`, preventing classpath conflicts with any MSAL version
the customer may already have.

---

## 5. Adding a New Driver Implementation

To add Entra ID support for a new language/driver:

### 5.1 Required Components

1. **Token Acquisition**: Use the language's MSAL library to get JWTs
2. **SASL PLAIN Response**: Build the `NUL + username + NUL + JWT` byte array
3. **AuthProvider Interface**: Implement the driver's auth provider interface

### 5.2 MSAL Libraries by Language

| Language | MSAL Library | Package |
|----------|-------------|---------|
| Java | MSAL4J | `com.microsoft.azure:msal4j:1.14.0` |
| C# | MSAL.NET | `Microsoft.Identity.Client` (NuGet) |
| Python | MSAL Python | `msal` (pip) |
| Go | MSAL Go | `github.com/AzureAD/microsoft-authentication-library-for-go` |
| Node.js | MSAL Node | `@azure/msal-node` (npm) |
| Rust | — | Use `reqwest` + manual OAuth2 (no official MSAL) |

### 5.3 Template

```pseudocode
class EntraIdAuthProvider implements DriverAuthProvider:
    
    constructor(tenant_id, client_id, client_secret, ...):
        store config
    
    newAuthenticator(host):
        return EntraIdAuthenticator(this)

class EntraIdAuthenticator implements DriverAuthenticator:
    
    initialResponse():
        token = acquireToken()  // via MSAL
        username = config.username or "entra-token"
        return bytes(NUL + username + NUL + token)
    
    evaluateChallenge(challenge):
        return null  // SASL PLAIN has no challenge
```

### 5.4 Go Driver Example (DataStax gocql)

```go
package entraauth

import (
    "context"
    "github.com/gocql/gocql"
    "github.com/AzureAD/microsoft-authentication-library-for-go/apps/confidential"
)

type EntraIdAuthenticator struct {
    TenantID     string
    ClientID     string
    ClientSecret string
}

func (a *EntraIdAuthenticator) Challenge(req []byte) ([]byte, gocql.Authenticator, error) {
    // Acquire token
    cred, _ := confidential.NewCredFromSecret(a.ClientSecret)
    client, _ := confidential.New("https://login.microsoftonline.com/"+a.TenantID, a.ClientID, cred)
    result, _ := client.AcquireTokenByCredential(context.Background(), 
        []string{"api://" + a.ClientID + "/.default"})
    
    token := result.AccessToken
    username := "entra-token"
    
    // SASL PLAIN
    resp := make([]byte, 0, 1+len(username)+1+len(token))
    resp = append(resp, 0)
    resp = append(resp, []byte(username)...)
    resp = append(resp, 0)
    resp = append(resp, []byte(token)...)
    
    return resp, nil, nil
}

func (a *EntraIdAuthenticator) Success(data []byte) error {
    return nil
}
```

---

## 6. Extending the Feature

### 6.1 Adding Multi-Tenant Support

To accept tokens from multiple tenants:

```java
// In EntraIdTokenValidator constructor
// Accept a comma-separated list of tenant IDs
String[] tenants = tenantId.split(",");
for (String t : tenants) {
    allowedIssuers.add("https://login.microsoftonline.com/" + t.trim() + "/v2.0");
    allowedIssuers.add("https://sts.windows.net/" + t.trim() + "/");
}
```

### 6.2 Adding Token Refresh

For long-lived sessions, implement background token refresh:

```java
// In EntraIdSaslNegotiator or as a scheduled task
ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();
scheduler.scheduleAtFixedRate(() -> {
    // Re-validate cached claims against fresh tokens
    // Evict entries where the original token has expired
    for (Map.Entry<String, EntraIdClaims> entry : claimsCache.entrySet()) {
        if (isClaimsExpired(entry.getValue())) {
            claimsCache.remove(entry.getKey());
        }
    }
}, 5, 5, TimeUnit.MINUTES);
```

### 6.3 Adding Conditional Access Support

Entra ID conditional access policies can require additional claims (e.g., compliant device,
specific IP range). These are enforced at token issuance time (client side), not at
validation time (server side). No server changes needed.

---

## 7. Debugging Guide

### 7.1 Enable Debug Logging

In `conf/logback.xml`:

```xml
<!-- EntraID auth debug logging -->
<logger name="org.apache.cassandra.auth.EntraIdAuthenticator" level="DEBUG"/>
<logger name="org.apache.cassandra.auth.EntraIdTokenValidator" level="DEBUG"/>
<logger name="org.apache.cassandra.auth.EntraIdAuthorizer" level="DEBUG"/>
```

### 7.2 Common Debug Scenarios

**Token contents inspection:**
```bash
# Decode a JWT (without verification)
echo "eyJhbGc..." | python3 -c "
import sys, json, base64
token = sys.stdin.read().strip()
parts = token.split('.')
header = json.loads(base64.urlsafe_b64decode(parts[0] + '=='))
payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
print('Header:', json.dumps(header, indent=2))
print('Payload:', json.dumps(payload, indent=2))
"
```

**Verify JWKS endpoint is reachable from Cassandra node:**
```bash
curl -s https://login.microsoftonline.com/YOUR_TENANT_ID/discovery/v2.0/keys | python3 -m json.tool
```

**Check if group claims are present in token:**
```bash
# Get a token and check for groups
TOKEN=$(az account get-access-token --resource api://YOUR_CLIENT_ID --query accessToken -o tsv)
echo $TOKEN | cut -d. -f2 | base64 -d 2>/dev/null | python3 -c "
import sys, json
payload = json.loads(sys.stdin.read())
print('Groups:', payload.get('groups', 'NOT PRESENT'))
print('Roles:', payload.get('roles', 'NOT PRESENT'))
"
```

### 7.3 JMX Monitoring

Key JMX beans to monitor:
- `org.apache.cassandra.metrics:type=Client,name=AuthSuccess` — successful auth count
- `org.apache.cassandra.metrics:type=Client,name=AuthFailure` — failed auth count

---

## 8. Code Style & Conventions

### 8.1 Cassandra Code Style

- 4-space indentation (no tabs)
- Opening braces on new line for classes, same line for methods
- `IAuthenticator` pattern: interface name starts with `I`
- `CassandraRoleManager` pattern: default implementations prefixed with `Cassandra` or named descriptively
- Logger: `private static final Logger logger = LoggerFactory.getLogger(ClassName.class);`
- Exceptions: `AuthenticationException` for auth failures, `ConfigurationException` for config

### 8.2 Exception Messages

Follow Cassandra's convention of actionable error messages:
```java
// Good
throw new ConfigurationException("entra_tenant_id must be configured in cassandra.yaml "
    + "or set via -Dcassandra.entra.tenant_id system property "
    + "when using EntraIdAuthenticator");

// Bad
throw new ConfigurationException("Missing tenant ID");
```

### 8.3 Dependency Rules

- **Server side**: No new dependencies. Use JDK + existing Cassandra deps only.
- **Client side**: MSAL is the only required addition. Azure.Identity is optional.
- **Test side**: Can use any test-scope dependency.
