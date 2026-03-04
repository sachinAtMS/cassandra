# Cassandra Entra ID Auth - Driver Plugins

Plug-and-play authentication plugins that enable Microsoft Entra ID (Azure AD)
token-based authentication for Apache Cassandra client drivers.

These plugins work with the server-side `EntraIdAuthenticator` and acquire JWT
tokens from Microsoft Entra ID using MSAL, then authenticate via SASL PLAIN.

## Available Plugins

| Language | Package | Artifact |
|----------|---------|----------|
| **Java (Driver 3.x)** | `cassandra-entra-id-auth-driver3` | Maven JAR / Uber JAR |
| **Java (Driver 4.x)** | `cassandra-entra-id-auth-driver4` | Maven JAR / Uber JAR |
| **C# (.NET)** | `Cassandra.Auth.EntraId` | NuGet Package |
| **Python** | `cassandra-entra-id-auth` | pip wheel/sdist |

## Quick Start

### Java (Maven)
```xml
<dependency>
    <groupId>org.apache.cassandra</groupId>
    <artifactId>cassandra-entra-id-auth-driver3</artifactId>  <!-- or driver4 -->
    <version>1.0.0</version>
</dependency>
```

### C# (NuGet)
```bash
dotnet add package Cassandra.Auth.EntraId --version 1.0.0
```

### Python (pip)
```bash
pip install cassandra-entra-id-auth
```

## Building All Plugins

### Linux / macOS
```bash
chmod +x build-all.sh
./build-all.sh          # Build all
./build-all.sh java     # Java only
./build-all.sh csharp   # C# only
./build-all.sh python   # Python only
```

### Windows
```cmd
build-all.bat           REM Build all
build-all.bat java      REM Java only
build-all.bat csharp    REM C# only
build-all.bat python    REM Python only
```

## Build Output

After building, distributable artifacts are found at:

```
java/driver3/target/cassandra-entra-id-auth-driver3-1.0.0.jar         # Thin JAR
java/driver3/target/cassandra-entra-id-auth-driver3-1.0.0-all.jar     # Uber JAR (recommended)
java/driver4/target/cassandra-entra-id-auth-driver4-1.0.0.jar
java/driver4/target/cassandra-entra-id-auth-driver4-1.0.0-all.jar

csharp/Cassandra.Auth.EntraId/bin/Release/Cassandra.Auth.EntraId.1.0.0.nupkg

python/dist/cassandra_entra_id_auth-1.0.0.tar.gz
python/dist/cassandra_entra_id_auth-1.0.0-py3-none-any.whl
```

## Authentication Flows

All plugins support the same set of authentication flows:

| Flow | Description | Recommended For |
|------|-------------|-----------------|
| **Client Credentials** | Service principal with client secret | Production service-to-service |
| **Managed Identity** | Azure-assigned identity (no secrets) | Azure VMs, AKS, App Service |
| **Default Credential** | Auto-detect available credential | Azure-hosted apps (most flexible) |
| **ROPC** | Username + password | Dev/test only |
| **Pre-acquired Token** | Externally obtained JWT | CLI tools, custom flows |

## Architecture

```
┌─────────────────────┐     SASL PLAIN        ┌──────────────────────┐
│  Client Application │ ──(NUL+user+NUL+JWT)──▶│  Cassandra Server    │
│                     │                        │                      │
│  ┌───────────────┐  │                        │  ┌────────────────┐  │
│  │ EntraId       │  │                        │  │ EntraId        │  │
│  │ AuthProvider  │  │                        │  │ Authenticator  │  │
│  │ (this plugin) │  │                        │  │ (server-side)  │  │
│  └──────┬────────┘  │                        │  └───────┬────────┘  │
│         │           │                        │          │           │
│  ┌──────▼────────┐  │                        │  ┌───────▼────────┐  │
│  │ MSAL Library  │  │                        │  │ Token Validator│  │
│  └──────┬────────┘  │                        │  └───────┬────────┘  │
└─────────┼───────────┘                        └──────────┼───────────┘
          │                                               │
          ▼                                               ▼
   ┌──────────────┐                              ┌──────────────┐
   │ Microsoft    │                              │ Microsoft    │
   │ Entra ID     │◀─────── JWKS/OIDC ──────────│ Entra ID     │
   │ (token)      │                              │ (validate)   │
   └──────────────┘                              └──────────────┘
```

## Prerequisites

- Server-side: Apache Cassandra 4.1+ with `EntraIdAuthenticator` configured
- Azure: Application registration in Microsoft Entra ID
- Network: Access to `login.microsoftonline.com` from both client and server

See the [documentation](../doc/modules/cassandra/pages/entra-id/) for full setup guides.

## License

Apache License, Version 2.0
