# Cassandra EntraID Authentication Plugin

A drop-in plugin JAR that adds Microsoft Entra ID (Azure AD) authentication and
group-based authorization to Apache Cassandra **without modifying any Cassandra
source code**.

## Features

- **Token-based authentication** — Clients send an Entra ID JWT token via SASL PLAIN.
- **RS256 signature verification** — Validates tokens against Microsoft's JWKS endpoint (JDK-only, no external JWT libraries).
- **Group-based authorization** — Maps Entra ID group memberships and app roles to Cassandra permission roles.
- **Zero source modifications** — Drop the JAR in `lib/`, add a properties file, and update `cassandra.yaml`.

## Quick Start

### 1. Build the plugin

```bash
cd server-plugin
mvn clean package
```

Output: `target/cassandra-entra-id-auth-1.0.0.jar`

### 2. Deploy

```bash
# Copy the JAR
cp target/cassandra-entra-id-auth-1.0.0.jar $CASSANDRA_HOME/lib/

# Copy and edit the config file
cp conf/entra-id.properties.example $CASSANDRA_HOME/conf/entra-id.properties
```

Edit `$CASSANDRA_HOME/conf/entra-id.properties`:
```properties
tenant_id=YOUR-TENANT-ID
client_id=YOUR-CLIENT-ID
```

### 3. Configure Cassandra

Edit `$CASSANDRA_HOME/conf/cassandra.yaml`:
```yaml
authenticator: org.apache.cassandra.auth.EntraIdAuthenticator
authorizer: org.apache.cassandra.auth.EntraIdAuthorizer
role_manager: CassandraRoleManager
```

### 4. Restart Cassandra

```bash
nodetool drain
# Stop and start Cassandra
```

## Configuration Methods

The plugin supports three configuration methods (checked in this order):

| Method | How | When to use |
|--------|-----|-------------|
| **JVM system properties** | `-Dcassandra.entra.tenant_id=... -Dcassandra.entra.client_id=...` in `jvm-server.options` | Containerized / orchestrated deployments |
| **Properties file** (default) | `$CASSANDRA_HOME/conf/entra-id.properties` | Standard deployments |
| **Custom file path** | `-Dcassandra.entra.config=/path/to/file` in `jvm-server.options` | Non-standard directory layouts |

### JVM System Properties

Add to `$CASSANDRA_HOME/conf/jvm-server.options`:
```
-Dcassandra.entra.tenant_id=72f988bf-86f1-41af-91ab-2d7cd011db47
-Dcassandra.entra.client_id=6731de76-14a6-49ae-97bc-6eba6914391e
```

### Properties File

Copy the example and edit:
```bash
cp conf/entra-id.properties.example $CASSANDRA_HOME/conf/entra-id.properties
```

### Custom Config Path

```
-Dcassandra.entra.config=/etc/cassandra/entra-id.properties
```

## How Authentication Works

1. Client connects using SASL PLAIN with:
   - **Username**: User's email / UPN (or any string — the token is authoritative)
   - **Password**: The JWT access token obtained from Entra ID

2. The plugin:
   - Decodes the JWT header, payload, and signature
   - Fetches Microsoft's JWKS keys (cached for 24 hours)
   - Verifies the RS256 signature
   - Validates `iss`, `aud`, `exp`, `nbf` claims
   - Extracts the principal name, groups, and app roles
   - Creates/resolves a Cassandra role for the user

## How Authorization Works

The `EntraIdAuthorizer` extends `CassandraAuthorizer` and adds group-based permissions:

1. **Direct role permissions** — Standard `system_auth.role_permissions` lookup
2. **Group-mapped permissions** — Entra ID groups are mapped to Cassandra roles via `system_auth.entra_group_roles`

### Setting Up Group Mappings

```cql
-- Map an Entra ID group to a Cassandra role
INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)
    VALUES ('aad-group-object-id', 'db_readers');

-- Map an App Role to a Cassandra role
INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)
    VALUES ('CassandraAdmin', 'cassandra_superuser');
```

## Compatibility

| Component | Version |
|-----------|---------|
| Apache Cassandra | 4.1.x |
| Java | 8+ (compiled with source/target 1.8) |
| Runtime dependencies | None (uses JDK crypto + Cassandra's bundled Jackson) |

## Project Structure

```
server-plugin/
├── pom.xml                          # Maven build
├── conf/
│   └── entra-id.properties.example  # Example configuration
├── src/
│   ├── main/java/org/apache/cassandra/auth/
│   │   ├── EntraIdAuthenticator.java    # IAuthenticator implementation
│   │   ├── EntraIdTokenValidator.java   # JWT validation (JDK-only)
│   │   └── EntraIdAuthorizer.java       # Group-based IAuthorizer
│   └── test/java/org/apache/cassandra/auth/
│       └── EntraIdAuthenticatorTest.java # Unit tests
└── README.md
```

## Building

### Prerequisites

- JDK 8 or later
- Maven 3.6+

### Build & Test

```bash
mvn clean verify
```

### Build Without Tests

```bash
mvn clean package -DskipTests
```

## Azure Setup

For detailed instructions on configuring the Entra ID App Registration,
see [AZURE-SETUP-GUIDE.md](../doc/modules/cassandra/pages/entra-id/AZURE-SETUP-GUIDE.md).

## Client Drivers

Pre-built authentication providers are available for:

| Language | Package |
|----------|---------|
| Java (Driver 3.x) | `org.apache.cassandra:cassandra-entra-id-auth-driver3` |
| Java (Driver 4.x) | `org.apache.cassandra:cassandra-entra-id-auth-driver4` |
| C# (.NET) | `Apache.Cassandra.EntraIdAuth` (NuGet) |
| Python | `cassandra-entra-id-auth` (pip) |

See the [driver-plugins/](../driver-plugins/) directory for source and build instructions.

## License

Apache License 2.0 — same as Apache Cassandra.
