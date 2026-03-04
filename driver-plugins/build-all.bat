@echo off
REM Licensed to the Apache Software Foundation (ASF) under one
REM or more contributor license agreements.
REM
REM Build script for Cassandra Entra ID Auth driver plugins (Windows).
REM Produces distributable binaries: JARs, NuGet package, and Python wheel.
REM
REM Usage:
REM   build-all.bat          Build everything
REM   build-all.bat java     Build Java only
REM   build-all.bat csharp   Build C# only
REM   build-all.bat python   Build Python only

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "BUILD_TARGET=%~1"
if "%BUILD_TARGET%"=="" set "BUILD_TARGET=all"

echo ================================================
echo  Cassandra Entra ID Auth - Driver Plugin Build
echo ================================================
echo.

if /i "%BUILD_TARGET%"=="java" goto :build_java
if /i "%BUILD_TARGET%"=="csharp" goto :build_csharp
if /i "%BUILD_TARGET%"=="dotnet" goto :build_csharp
if /i "%BUILD_TARGET%"=="python" goto :build_python
if /i "%BUILD_TARGET%"=="pip" goto :build_python
if /i "%BUILD_TARGET%"=="all" goto :build_all

echo ERROR: Unknown target: %BUILD_TARGET%
echo Usage: %~0 [java^|csharp^|python^|all]
exit /b 1

:build_all
call :build_java
if errorlevel 1 exit /b 1
echo.
call :build_csharp
if errorlevel 1 exit /b 1
echo.
call :build_python
if errorlevel 1 exit /b 1
goto :done

:build_java
echo [INFO] Building Java driver plugins...
cd /d "%SCRIPT_DIR%java"
where mvn >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Maven ^(mvn^) not found. Install Maven 3.6+ to build Java plugins.
    exit /b 1
)
call mvn clean package -DskipTests
if errorlevel 1 (
    echo [ERROR] Java build failed.
    exit /b 1
)
echo [INFO] Java build complete. Artifacts:
echo   driver3\target\cassandra-entra-id-auth-driver3-1.0.0.jar
echo   driver3\target\cassandra-entra-id-auth-driver3-1.0.0-all.jar  (uber JAR)
echo   driver4\target\cassandra-entra-id-auth-driver4-1.0.0.jar
echo   driver4\target\cassandra-entra-id-auth-driver4-1.0.0-all.jar  (uber JAR)
cd /d "%SCRIPT_DIR%"
exit /b 0

:build_csharp
echo [INFO] Building C# driver plugin...
cd /d "%SCRIPT_DIR%csharp"
where dotnet >nul 2>&1
if errorlevel 1 (
    echo [ERROR] dotnet SDK not found. Install .NET 6.0+ SDK to build C# plugin.
    exit /b 1
)
dotnet restore
if errorlevel 1 exit /b 1
dotnet build -c Release
if errorlevel 1 exit /b 1
dotnet pack -c Release --no-build
if errorlevel 1 exit /b 1
echo [INFO] C# build complete. Artifact:
echo   Cassandra.Auth.EntraId\bin\Release\Cassandra.Auth.EntraId.1.0.0.nupkg
cd /d "%SCRIPT_DIR%"
exit /b 0

:build_python
echo [INFO] Building Python driver plugin...
cd /d "%SCRIPT_DIR%python"
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.7+ to build Python plugin.
    exit /b 1
)
python -m pip install --quiet build 2>nul
python -m build
if errorlevel 1 (
    echo [ERROR] Python build failed.
    exit /b 1
)
echo [INFO] Python build complete. Artifacts:
echo   dist\cassandra_entra_id_auth-1.0.0.tar.gz
echo   dist\cassandra_entra_id_auth-1.0.0-py3-none-any.whl
cd /d "%SCRIPT_DIR%"
exit /b 0

:done
echo.
echo [INFO] Build finished successfully!
