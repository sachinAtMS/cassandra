# Entra ID Authentication for Apache Cassandra — User Guide

A step-by-step guide for **operators and end users** to set up and use Microsoft Entra ID
(Azure AD) authentication with Apache Cassandra.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Quick Start](#3-quick-start)
4. [Cassandra Server Configuration](#4-cassandra-server-configuration)
5. [Connecting with CQLSH](#5-connecting-with-cqlsh)
6. [Connecting with Java Applications](#6-connecting-with-java-applications)
7. [Connecting with .NET Applications](#7-connecting-with-net-applications)
8. [Connecting with Python Applications](#8-connecting-with-python-applications)
9. [Managing Group-to-Role Mappings](#9-managing-group-to-role-mappings)
10. [Token Lifecycle & Session Management](#10-token-lifecycle--session-management)
11. [Monitoring & Troubleshooting](#11-monitoring--troubleshooting)
12. [FAQ](#12-faq)

---

## 1. Overview

Entra ID authentication replaces username/password authentication with JWT-based identity
verification. Instead of managing passwords in Cassandra, user identities are managed in
Microsoft Entra ID (formerly Azure AD).

**Key benefits:**
- Centralized identity management via Azure Portal
- Multi-factor authentication support
- Group-based role assignment (no per-user grants)
- Token expiration and rotation (no long-lived passwords)
- Audit trail in Azure Monitor

**How it works (simplified):**

```
1. User/app gets a JWT token from Entra ID
2. Client driver sends token to Cassandra via SASL PLAIN
3. Cassandra validates the token signature, expiry, audience, issuer
4. Cassandra extracts the user identity from the token
5. Cassandra checks group memberships for authorization
```

---

## 2. Prerequisites

### Azure Side
- An Azure subscription
- Admin access to Entra ID (Azure AD)
- An App Registration (see [Azure Setup Guide](AZURE-SETUP-GUIDE.md) for creation steps)
- Users or service principals assigned to the application

### Cassandra Side
- Apache Cassandra 4.1+ with Entra ID auth classes deployed (see deployment options below)
- Network access from Cassandra nodes to `login.microsoftonline.com` (HTTPS/443)
- JDK 11+

### Client Side
- MSAL library for your language (msal4j, MSAL.NET, msal-python)
- The App Registration's Tenant ID and Client ID

---

## 3. Quick Start

This section gets you from zero to a working connection in the minimum number of steps.

### Step 1 — Deploy Server-Side Components

**Option A — Plugin JAR (Recommended, no source modifications):**

```bash
# Build the plugin
cd server-plugin && mvn clean package

# Copy JAR and config
cp target/cassandra-entra-id-auth-1.0.0.jar $CASSANDRA_HOME/lib/
cp conf/entra-id.properties.example $CASSANDRA_HOME/conf/entra-id.properties
```

Edit `$CASSANDRA_HOME/conf/entra-id.properties`:
```properties
tenant_id=YOUR-TENANT-ID
client_id=YOUR-CLIENT-ID
```

**Option B — Source Integration (requires building Cassandra from source):**

Add `entra_tenant_id` and `entra_client_id` fields to `cassandra.yaml`.

### Step 2 — Configure Cassandra

Edit `conf/cassandra.yaml`:

```yaml
authenticator: EntraIdAuthenticator
authorizer: EntraIdAuthorizer
role_manager: CassandraRoleManager
```

If using Option B (source integration), also add:
```yaml
entra_tenant_id: YOUR-TENANT-ID
entra_client_id: YOUR-CLIENT-ID
```

Restart all Cassandra nodes.

### Step 2 — Connect with CQLSH (Service Principal)

Create `~/.cassandra/cqlshrc`:

```ini
[auth_provider]
module = cqlshlib.entra_id_auth_provider
classname = EntraIdAuthProvider
tenant_id = YOUR-TENANT-ID
client_id = YOUR-CLIENT-ID
client_secret = YOUR-CLIENT-SECRET
```

The Entra ID auth provider module ships with Cassandra in `pylib/cqlshlib/`. No
manual file copying is required — just configure the cqlshrc and run:

```bash
cqlsh --cqlshrc=~/.cassandra/cqlshrc your-cassandra-host
```

### Step 3 — Verify

```sql
-- Should show your Entra ID principal as the logged-in user
SELECT * FROM system.local;
```

---

## 4. Cassandra Server Configuration

### 4.0 Deployment Options

| Option | JAR Location | Config Method | Source Modification |
|--------|-------------|---------------|---------------------|
| **Plugin JAR** (recommended) | `$CASSANDRA_HOME/lib/cassandra-entra-id-auth-1.0.0.jar` | Properties file or JVM system properties | None |
| **Source Integration** | Built into `cassandra-all` | `cassandra.yaml` fields or JVM system properties | Requires `Config.java` changes |

### 4.1 cassandra.yaml Settings

| Setting | Required | Description |
|---------|----------|-------------|
| `authenticator` | Yes | Set to `EntraIdAuthenticator` |
| `authorizer` | Yes | Set to `EntraIdAuthorizer` (or `CassandraAuthorizer` for no group mapping) |
| `role_manager` | Yes | Keep as `CassandraRoleManager` |
| `entra_tenant_id` | Source only | Your Azure Active Directory tenant ID (GUID) |
| `entra_client_id` | Source only | Your App Registration's Application (client) ID (GUID) |

### 4.2 Plugin Configuration (Properties File)

When using the plugin JAR, create `$CASSANDRA_HOME/conf/entra-id.properties`:

```properties
tenant_id=YOUR-TENANT-ID
client_id=YOUR-CLIENT-ID
```

The plugin searches for the properties file in this order:
1. Path from `-Dcassandra.entra.config=/path/to/file`
2. `$CASSANDRA_HOME/conf/entra-id.properties`
3. `conf/entra-id.properties` (relative to working directory)

### 4.3 System Property Overrides

You can also set tenant and client ID via JVM system properties (useful for containerized deployments):

```bash
# In jvm-server.options or via command line
-Dcassandra.entra.tenant_id=YOUR-TENANT-ID
-Dcassandra.entra.client_id=YOUR-CLIENT-ID
```

System properties take precedence over cassandra.yaml values.

### 4.3 Creating Cassandra Roles

After enabling Entra ID auth, you need to create Cassandra roles that match your Entra ID
users. The role name should match the user's principal name:

```sql
-- Connect as a superuser first (bootstrap the first superuser role)
-- Note: First connection requires temporarily allowing password auth or using a superuser token.

-- Create roles that match Entra ID principal names
CREATE ROLE 'alice@contoso.com' WITH LOGIN = true;
CREATE ROLE 'bob@contoso.com' WITH LOGIN = true;

-- Grant permissions
GRANT SELECT ON KEYSPACE my_app TO 'alice@contoso.com';
GRANT ALL ON KEYSPACE my_app TO 'bob@contoso.com';
```

### 4.4 Rolling Upgrade

To migrate from PasswordAuthenticator to EntraIdAuthenticator without downtime:

1. **Deploy Entra ID JAR** to all nodes (add to classpath if external)
2. **Create Entra ID roles** alongside existing password roles
3. **Switch one node at a time**: update cassandra.yaml, restart
4. **Update client drivers** to use Entra ID auth providers
5. **Remove old password roles** after all clients are migrated

> **Warning**: During rolling upgrade, some nodes use password auth and others use token auth.
> Ensure clients can handle both by detecting the authenticator FQCN in the AUTHENTICATE response.

---

## 5. Connecting with CQLSH

### 5.1 Install Dependencies

```bash
pip install msal azure-identity cassandra-driver
```

### 5.2 Configure cqlshrc

The Entra ID auth provider ships with Cassandra in `pylib/cqlshlib/entra_id_auth_provider.py`.
No additional installation is required beyond the MSAL dependency.

**Service Principal (client credentials):**

```ini
[auth_provider]
module = cqlshlib.entra_id_auth_provider
classname = EntraIdAuthProvider
tenant_id = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
client_id = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
client_secret = your-client-secret-value
```

**Username/Password (ROPC — interactive user):**

```ini
[auth_provider]
module = cqlshlib.entra_id_auth_provider
classname = EntraIdAuthProvider
tenant_id = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
client_id = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
username = alice@contoso.com
password = UserPassword123
```

**Managed Identity (Azure VM, AKS, App Service):**

```ini
[auth_provider]
module = cqlshlib.entra_id_auth_provider
classname = EntraIdAuthProvider
client_id = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
use_managed_identity = true
```

**Default Azure Credential (developer workstation):**

```ini
[auth_provider]
module = cqlshlib.entra_id_auth_provider
classname = EntraIdAuthProvider
client_id = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
use_default_credential = true
```

### 5.4 Run CQLSH

```bash
# With default cqlshrc location (~/.cassandra/cqlshrc)
cqlsh your-host 9042

# With explicit cqlshrc path
cqlsh --cqlshrc=/path/to/cqlshrc your-host 9042

# With SSL (recommended for production)
cqlsh --ssl --cqlshrc=/path/to/cqlshrc your-host 9042
```

---

## 6. Connecting with Java Applications

### 6.1 Dependencies

**Option A — Pre-Built Plugin (Recommended):**

Use the pre-built uber JAR which bundles MSAL4J with relocated packages:

```xml
<!-- Maven (Driver 3.x) -->
<dependency>
    <groupId>org.apache.cassandra</groupId>
    <artifactId>cassandra-entra-id-auth-driver3</artifactId>
    <version>1.0.0</version>
</dependency>

<!-- Maven (Driver 4.x) -->
<dependency>
    <groupId>org.apache.cassandra</groupId>
    <artifactId>cassandra-entra-id-auth-driver4</artifactId>
    <version>1.0.0</version>
</dependency>
```

The plugin JARs are also available as standalone uber JARs (`-all.jar` classifier)
for non-Maven projects. Build from source via `driver-plugins/java/`.

**Option B — Manual Dependencies:**

**Maven (Driver 3.x):**
```xml
<dependency>
    <groupId>com.datastax.cassandra</groupId>
    <artifactId>cassandra-driver-core</artifactId>
    <version>3.11.3</version>
</dependency>
<dependency>
    <groupId>com.microsoft.azure</groupId>
    <artifactId>msal4j</artifactId>
    <version>1.14.0</version>
</dependency>
```

**Maven (Driver 4.x):**
```xml
<dependency>
    <groupId>com.datastax.oss</groupId>
    <artifactId>java-driver-core</artifactId>
    <version>4.17.0</version>
</dependency>
<dependency>
    <groupId>com.microsoft.azure</groupId>
    <artifactId>msal4j</artifactId>
    <version>1.14.0</version>
</dependency>
```

### 6.2 Usage Examples

**Driver 3.x — Service Principal:**
```java
import com.datastax.driver.core.Cluster;
import com.datastax.driver.core.Session;

EntraIdAuthProvider authProvider = EntraIdAuthProvider.builder()
    .tenantId("your-tenant-id")
    .clientId("your-client-id")
    .clientSecret("your-secret")
    .build();

Cluster cluster = Cluster.builder()
    .addContactPoint("cassandra-host")
    .withPort(9042)
    .withAuthProvider(authProvider)
    .withSSL()   // Recommended
    .build();

Session session = cluster.connect();
session.execute("SELECT * FROM system.local");
```

**Driver 4.x — Managed Identity:**
```java
import com.datastax.oss.driver.api.core.CqlSession;

EntraIdAuthProviderV4 authProvider = EntraIdAuthProviderV4.builder()
    .clientId("your-client-id")
    .useManagedIdentity(true)
    .build();

CqlSession session = CqlSession.builder()
    .addContactPoint(new InetSocketAddress("cassandra-host", 9042))
    .withAuthProvider(authProvider)
    .build();

session.execute("SELECT * FROM system.local");
```

### 6.3 Spring Boot Configuration

```java
@Configuration
public class CassandraConfig {
    
    @Value("${entra.tenant-id}") String tenantId;
    @Value("${entra.client-id}") String clientId;
    @Value("${entra.client-secret}") String clientSecret;
    
    @Bean
    public CqlSession cqlSession() {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("cassandra-host", 9042))
            .withAuthProvider(EntraIdAuthProviderV4.builder()
                .tenantId(tenantId)
                .clientId(clientId)
                .clientSecret(clientSecret)
                .build())
            .withLocalDatacenter("datacenter1")
            .build();
    }
}
```

`application.properties`:
```properties
entra.tenant-id=${ENTRA_TENANT_ID}
entra.client-id=${ENTRA_CLIENT_ID}
entra.client-secret=${ENTRA_CLIENT_SECRET}
```

---

## 7. Connecting with .NET Applications

### 7.1 Dependencies

**Option A — Pre-Built NuGet Package (Recommended):**

```bash
dotnet add package Cassandra.Auth.EntraId
```

This transitively pulls in `CassandraCSharpDriver`, `Microsoft.Identity.Client`, and
`Azure.Identity`. Build from source via `driver-plugins/csharp/`.

**Option B — Manual Dependencies:**

```xml
<!-- NuGet packages -->
<PackageReference Include="CassandraCSharpDriver" Version="3.19.5" />
<PackageReference Include="Microsoft.Identity.Client" Version="4.56.0" />
<!-- Optional: for DefaultAzureCredential -->
<PackageReference Include="Azure.Identity" Version="1.10.2" />
```

### 7.2 Usage Examples

**Service Principal:**
```csharp
using Cassandra;

var authProvider = new EntraIdAuthProvider(
    tenantId: "your-tenant-id",
    clientId: "your-client-id",
    clientSecret: "your-secret"
);

var cluster = Cluster.Builder()
    .AddContactPoint("cassandra-host")
    .WithPort(9042)
    .WithAuthProvider(authProvider)
    .WithSSL()
    .Build();

var session = cluster.Connect();
var rs = session.Execute("SELECT * FROM system.local");
```

**Managed Identity:**
```csharp
var authProvider = EntraIdAuthProvider.WithManagedIdentity("your-client-id");

var cluster = Cluster.Builder()
    .AddContactPoint("cassandra-host")
    .WithAuthProvider(authProvider)
    .Build();
```

**Default Credential (developer workstation, `az login`):**
```csharp
var authProvider = EntraIdAuthProvider.WithDefaultCredential("your-client-id");

var cluster = Cluster.Builder()
    .AddContactPoint("cassandra-host")
    .WithAuthProvider(authProvider)
    .Build();
```

### 7.3 ASP.NET Configuration

```csharp
// Program.cs
builder.Services.AddSingleton<ICluster>(sp =>
{
    var config = sp.GetRequiredService<IConfiguration>();
    var authProvider = new EntraIdAuthProvider(
        tenantId: config["Entra:TenantId"],
        clientId: config["Entra:ClientId"],
        clientSecret: config["Entra:ClientSecret"]
    );
    return Cluster.Builder()
        .AddContactPoint(config["Cassandra:ContactPoint"])
        .WithAuthProvider(authProvider)
        .Build();
});
```

`appsettings.json`:
```json
{
  "Entra": {
    "TenantId": "your-tenant-id",
    "ClientId": "your-client-id",
    "ClientSecret": "your-secret"
  },
  "Cassandra": {
    "ContactPoint": "cassandra-host"
  }
}
```

---

## 8. Connecting with Python Applications

### 8.1 Dependencies

**Option A — Pre-Built pip Package (Recommended):**

```bash
pip install cassandra-entra-id-auth          # core (cassandra-driver + msal)
pip install cassandra-entra-id-auth[azure]    # adds azure-identity for DefaultAzureCredential
```

Build from source via `driver-plugins/python/`.

**Option B — Manual Dependencies:**

```bash
pip install cassandra-driver msal azure-identity
```

### 8.2 Usage Examples

**Service Principal:**
```python
from cassandra.cluster import Cluster
from cassandra_entra_id_auth import EntraIdAuthProvider

auth_provider = EntraIdAuthProvider(
    tenant_id='your-tenant-id',
    client_id='your-client-id',
    client_secret='your-secret'
)

cluster = Cluster(
    contact_points=['cassandra-host'],
    port=9042,
    auth_provider=auth_provider
)
session = cluster.connect()
rows = session.execute("SELECT * FROM system.local")
```

**Managed Identity (Azure VM / AKS):**
```python
auth_provider = EntraIdAuthProvider(
    client_id='your-client-id',
    use_managed_identity=True
)
```

**Default Credential (developer workstation):**
```python
auth_provider = EntraIdAuthProvider(
    client_id='your-client-id',
    use_default_credential=True
)
```

**Pre-Acquired Token (advanced — bring your own token):**
```python
import msal

# Your own token acquisition logic
app = msal.ConfidentialClientApplication(
    client_id='your-client-id',
    authority='https://login.microsoftonline.com/your-tenant-id',
    client_credential='your-secret'
)
result = app.acquire_token_for_client(scopes=['api://your-client-id/.default'])
token = result['access_token']

auth_provider = EntraIdAuthProvider(
    client_id='your-client-id',
    token=token
)
```

### 8.3 Django Configuration

```python
# settings.py
CASSANDRA_AUTH = EntraIdAuthProvider(
    tenant_id=os.environ['ENTRA_TENANT_ID'],
    client_id=os.environ['ENTRA_CLIENT_ID'],
    client_secret=os.environ['ENTRA_CLIENT_SECRET'],
)

# In your app
from django.conf import settings
from cassandra.cluster import Cluster

cluster = Cluster(
    contact_points=['cassandra-host'],
    auth_provider=settings.CASSANDRA_AUTH,
)
```

---

## 9. Managing Group-to-Role Mappings

### 9.1 Creating Mappings

Group-to-role mappings allow Entra ID security groups to automatically receive Cassandra
permissions. This is the recommended approach for managing permissions at scale.

```sql
-- First, create the Cassandra roles
CREATE ROLE 'data_reader' WITH LOGIN = false;
CREATE ROLE 'data_writer' WITH LOGIN = false;
CREATE ROLE 'admin' WITH LOGIN = false AND SUPERUSER = true;

-- Grant permissions to roles
GRANT SELECT ON ALL KEYSPACES TO 'data_reader';
GRANT SELECT, MODIFY ON KEYSPACE production TO 'data_writer';
GRANT ALL PERMISSIONS ON ALL KEYSPACES TO 'admin';

-- Map Entra ID groups to Cassandra roles
-- Use the Entra ID group Object ID (visible in Azure Portal)
INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)
VALUES ('a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'data_reader');

INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)
VALUES ('b2c3d4e5-f6a7-8901-bcde-f12345678901', 'data_writer');

INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)
VALUES ('c3d4e5f6-a7b8-9012-cdef-123456789012', 'admin');
```

### 9.2 Viewing Mappings

```sql
-- List all group-to-role mappings
SELECT * FROM system_auth.entra_group_roles;

-- List mappings for a specific group
SELECT * FROM system_auth.entra_group_roles 
WHERE group_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';
```

### 9.3 Removing Mappings

```sql
DELETE FROM system_auth.entra_group_roles 
WHERE group_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890' 
AND cassandra_role = 'data_reader';
```

### 9.4 How Permissions Are Resolved

When a user authenticates, Cassandra resolves their effective permissions as:

```
Effective Permissions = 
    Direct Role Permissions (GRANT on user's Cassandra role)
  + Group-Mapped Permissions (via entra_group_roles for each group in JWT)
```

Example scenario:
- User `alice@contoso.com` has Cassandra role `alice@contoso.com`
- Alice is in Entra ID group `readers-group` (OID: `aaa-bbb-ccc`)
- `readers-group` is mapped to Cassandra role `data_reader`
- `alice@contoso.com` has direct `MODIFY` on `keyspace1`
- `data_reader` has `SELECT` on `ALL KEYSPACES`

Alice's effective permissions:
- `MODIFY` on `keyspace1` (from direct role)
- `SELECT` on `ALL KEYSPACES` (from group → data_reader)

---

## 10. Token Lifecycle & Session Management

### 10.1 Token Expiry

Entra ID tokens typically expire after **1 hour** (default). Token expireation is validated at
connection time only. Existing CQL sessions are not affected by token expiry — they remain
connected until the TCP session ends.

### 10.2 Reconnection

When a driver reconnects (e.g., node failover, connection pool refresh), a new token is
acquired automatically by the auth provider. Ensure your application's `clientSecret` or
managed identity remains valid.

### 10.3 Token Caching

The MSAL libraries cache tokens automatically and refresh them before expiry. You don't need
to implement caching yourself:
- MSAL Java: In-memory cache (default)
- MSAL .NET: In-memory cache (default), can persist to Redis/file
- MSAL Python: In-memory cache (default)

### 10.4 Graceful Rotation

To rotate a client secret:
1. Create a new secret in Azure Portal (App Registration → Certificates & secrets)
2. Update client applications with the new secret
3. Wait for all existing connections to drain (or restart apps)
4. Delete the old secret in Azure Portal

---

## 11. Monitoring & Troubleshooting

### 11.1 Common Error Messages

| Error Message | Cause | Fix |
|---------------|-------|-----|
| `JWT signature validation failed` | Token was tampered or signed by wrong key | Verify tenant_id matches in server config and client |
| `Token has expired` | JWT exp claim is in the past | Client is using a stale token — reconnect |
| `Invalid audience` | Token's `aud` claim doesn't match `entra_client_id` | Ensure scope is `api://{client_id}/.default` |
| `Invalid issuer` | Token's `iss` doesn't match expected tenant | Check `entra_tenant_id` in cassandra.yaml |
| `Unable to fetch JWKS from Microsoft` | Network issue | Check firewall rules — Cassandra needs HTTPS to `login.microsoftonline.com` |
| `entra_tenant_id must be configured` | Missing config | Add `entra_tenant_id` to cassandra.yaml or system property |
| `AADSTS700016: Application not found` | Wrong client_id in client config | Verify client_id matches App Registration |
| `AADSTS7000215: Invalid client secret` | Wrong or expired secret | Regenerate secret in Azure Portal |
| `AADSTS50034: User account not found` | User doesn't exist in tenant | Verify user exists in Entra ID |

### 11.2 Checking Authentication Status

```sql
-- Run these from a working connection:

-- Check current authenticator
SELECT * FROM system_schema.keyspaces WHERE keyspace_name = 'system_auth';

-- List all roles
LIST ROLES;

-- Check your effective permissions
LIST ALL PERMISSIONS OF 'your-username@contoso.com';
```

### 11.3 Diagnostic Commands

```bash
# Check token issuer
az account get-access-token --resource api://YOUR_CLIENT_ID \
  --query "{accessToken:accessToken}" -o json \
  | python3 -c "
import sys, json, base64
data = json.load(sys.stdin)
payload = json.loads(base64.urlsafe_b64decode(data['accessToken'].split('.')[1] + '=='))
print('Issuer:', payload['iss'])
print('Audience:', payload['aud'])
print('Expires:', payload['exp'])
print('Groups:', payload.get('groups', 'NOT PRESENT'))
"

# Test connectivity from Cassandra node
curl -v https://login.microsoftonline.com/YOUR_TENANT_ID/v2.0/.well-known/openid-configuration

# Verify DNS resolution
nslookup login.microsoftonline.com

# Check Cassandra auth logs
grep -i "entra\|auth\|jwt" /var/log/cassandra/system.log | tail -50
```

### 11.4 Health Checks

For production monitoring, verify:
1. **Cassandra nodes can reach Entra ID**: Test HTTPS to `login.microsoftonline.com`
2. **JWKS cache is fresh**: Check logs for JWKS fetch errors
3. **Token acquisition works**: Run a test connection every few minutes
4. **Client secrets haven't expired**: Set Azure Monitor alerts on secret expiry

---

## 12. FAQ

### General

**Q: Can I use Entra ID auth and password auth at the same time?**
A: Not on the same node. Each node has one `authenticator` configured. During migration,
you can run mixed clusters temporarily where some nodes use `PasswordAuthenticator` and
others use `EntraIdAuthenticator`.

**Q: Does this work with Cassandra Operator (K8ssandra, cass-operator)?**
A: Yes, configure the authenticator/authorizer in the operator's CassandraDatacenter spec.
Use Managed Identity for pods (via Azure Workload Identity).

**Q: What happens if Entra ID is down?**
A: New connections will fail because tokens can't be acquired. Existing connections remain
active. The JWKS cache on the server side allows signature verification to continue for
cached keys (24-hour TTL).

**Q: Can I use B2C tenants?**
A: Yes, update the `authority` URL to your B2C tenant's authority endpoint:
`https://yourtenant.b2clogin.com/yourtenant.onmicrosoft.com/B2C_1_signIn`

### Security

**Q: Is the token transmitted in plaintext?**
A: The token is sent via SASL PLAIN, which does not encrypt the payload. You **must** enable
SSL/TLS (`client_encryption_options` in cassandra.yaml) to protect tokens in transit.

**Q: How long are tokens valid?**
A: Default is 1 hour. This is configurable in Azure AD (Token Configuration → Access Token
Lifetime). Minimum is 10 minutes, maximum is 24 hours.

**Q: What signing algorithms are supported?**
A: RS256 (RSA-SHA256) only. This is the standard algorithm used by Entra ID.

### Troubleshooting

**Q: I get "groups claim not present" but I configured group claims.**
A: Check the App Registration's Token Configuration. Also, if the user is in more than 200
groups, Entra ID sends a `_claim_sources` URL instead of inline groups. The current
implementation requires inline groups (overage not supported).

**Q: My service principal can connect but gets no group-mapped permissions.**
A: Service principals use `roles` claim (app roles), not `groups` claim. Configure App Roles
in your App Registration and assign them to the service principal.

**Q: CQLSH says "No module named cqlshlib.entra_id_auth_provider".**
A: Ensure you're using a Cassandra distribution that includes the Entra ID auth provider
in `pylib/cqlshlib/entra_id_auth_provider.py`. If upgrading, verify the file is present.
Alternatively, copy the file from `examples/entra-id/python/entra_id_auth_provider.py`
to your Python path.
