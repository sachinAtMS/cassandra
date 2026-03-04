#!/bin/bash
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.
#
# Build script for all Cassandra Entra ID Auth driver plugins.
# Produces distributable binaries: JARs, NuGet package, and Python wheel.
#
# Usage:
#   ./build-all.sh          # Build everything
#   ./build-all.sh java     # Build Java only
#   ./build-all.sh csharp   # Build C# only
#   ./build-all.sh python   # Build Python only

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_TARGET="${1:-all}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ============================================================
# Java (Maven multi-module)
# ============================================================
build_java() {
    log_info "Building Java driver plugins..."
    cd "$SCRIPT_DIR/java"

    if ! command -v mvn &> /dev/null; then
        log_error "Maven (mvn) not found. Install Maven 3.6+ to build Java plugins."
        return 1
    fi

    mvn clean package -DskipTests

    log_info "Java build complete. Artifacts:"
    echo "  driver3/target/cassandra-entra-id-auth-driver3-1.0.0.jar"
    echo "  driver3/target/cassandra-entra-id-auth-driver3-1.0.0-all.jar  (uber JAR)"
    echo "  driver4/target/cassandra-entra-id-auth-driver4-1.0.0.jar"
    echo "  driver4/target/cassandra-entra-id-auth-driver4-1.0.0-all.jar  (uber JAR)"

    cd "$SCRIPT_DIR"
}

# ============================================================
# C# (.NET / NuGet)
# ============================================================
build_csharp() {
    log_info "Building C# driver plugin..."
    cd "$SCRIPT_DIR/csharp"

    if ! command -v dotnet &> /dev/null; then
        log_error "dotnet SDK not found. Install .NET 6.0+ SDK to build C# plugin."
        return 1
    fi

    dotnet restore
    dotnet build -c Release
    dotnet pack -c Release --no-build

    log_info "C# build complete. Artifact:"
    echo "  Cassandra.Auth.EntraId/bin/Release/Cassandra.Auth.EntraId.1.0.0.nupkg"

    cd "$SCRIPT_DIR"
}

# ============================================================
# Python (pip / wheel)
# ============================================================
build_python() {
    log_info "Building Python driver plugin..."
    cd "$SCRIPT_DIR/python"

    if ! command -v python3 &> /dev/null; then
        log_error "python3 not found. Install Python 3.7+ to build Python plugin."
        return 1
    fi

    # Ensure build module is available
    python3 -m pip install --quiet build 2>/dev/null || true

    python3 -m build

    log_info "Python build complete. Artifacts:"
    echo "  dist/cassandra_entra_id_auth-1.0.0.tar.gz"
    echo "  dist/cassandra_entra_id_auth-1.0.0-py3-none-any.whl"

    cd "$SCRIPT_DIR"
}

# ============================================================
# Main
# ============================================================
log_info "Cassandra Entra ID Auth - Driver Plugin Build"
echo "=============================================="

case "$BUILD_TARGET" in
    java)
        build_java
        ;;
    csharp|dotnet)
        build_csharp
        ;;
    python|pip)
        build_python
        ;;
    all)
        build_java
        echo ""
        build_csharp
        echo ""
        build_python
        ;;
    *)
        log_error "Unknown target: $BUILD_TARGET"
        echo "Usage: $0 [java|csharp|python|all]"
        exit 1
        ;;
esac

echo ""
log_info "Build finished successfully!"
