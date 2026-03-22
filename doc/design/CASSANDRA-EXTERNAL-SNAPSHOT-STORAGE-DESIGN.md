# External Snapshot Storage — Design Document

**Component**: Apache Cassandra Snapshot Subsystem  
**Cassandra Version**: 4.1.x  
**PR Reference**: CASSANDRA PR #4648  
**ML Thread**: "[DISCUSS] Snapshots outside of Cassandra data directory" (dev@cassandra.apache.org, Jan–Feb 2025)  
**Author**: Sachin Gupta  
**Date**: March 2026  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Background & Motivation](#2-background--motivation)
3. [Community Discussion — What Was Missing](#3-community-discussion--what-was-missing)
4. [Why the Gaps Existed in PR #4648](#4-why-the-gaps-existed-in-pr-4648)
5. [High-Level Design (HLD)](#5-high-level-design-hld)
6. [System Design — Detailed Architecture](#6-system-design--detailed-architecture)
7. [Configuration Reference](#7-configuration-reference)
8. [Directory Layout](#8-directory-layout)
9. [Deduplication & Reference-Counted Cleanup](#9-deduplication--reference-counted-cleanup)
10. [Nodetool Commands](#10-nodetool-commands)
11. [Files Changed — Complete Inventory](#11-files-changed--complete-inventory)
12. [What Changed and Why — Detailed Changelog](#12-what-changed-and-why--detailed-changelog)
13. [Test Coverage](#13-test-coverage)
14. [Live Testing Results & Runtime Bugs Discovered](#14-live-testing-results--runtime-bugs-discovered)
15. [3-Node Cluster Disaster Recovery & Restore Test](#15-3-node-cluster-disaster-recovery--restore-test)
16. [Future Considerations](#16-future-considerations)

---

## 1. Executive Summary

This document describes the redesigned **External Snapshot Storage** feature for Apache Cassandra 4.1.x. The feature allows user-initiated snapshots to be stored on a separate filesystem/mount point instead of using hardlinks within the data directory. This prevents snapshot growth from filling the data disk — a critical operational concern in production clusters.

The original PR #4648 proposed a basic copy-based approach. After extensive community review on the Apache dev mailing list (led by Štefan Miklošovič, with input from multiple committers), **10+ design gaps** were identified. This redesign addresses every concern raised in that discussion.

**Key capabilities delivered:**

| Capability | Status |
|---|---|
| Hierarchical per-node directory layout | ✅ |
| SSTable deduplication via UUID identifiers | ✅ |
| Reference-counted cleanup (no premature deletion) | ✅ |
| Enhanced manifests (tokens, schema, host_id) | ✅ |
| User-snapshot-only gating | ✅ |
| Bandwidth throttling for copy I/O | ✅ |
| Incremental backup support | ✅ |
| New nodetool commands (listexternalsnapshots, listbackups, clearbackups) | ✅ |
| 89 unit tests passing (15 new + 74 existing, 0 regressions) | ✅ |
| Live-tested: nodetool snapshot/list/clear with dedup & ref-count cleanup | ✅ |

---

## 2. Background & Motivation

### The Problem

Cassandra snapshots use hardlinks in the data directory. This is fast (no data copying) but has a critical operational drawback: **snapshots consume space on the same disk as live data**. In production environments:

- Operators cannot predict disk growth from snapshot accumulation
- A forgotten or TTL-misconfigured snapshot can fill the data disk, causing writes to fail
- Backup workflows that need snapshots to persist (e.g., for streaming to S3/GCS) compete with data for disk space
- There is no way to use a separate, cheaper, larger mount point for snapshot storage

### The Original PR #4648

PR #4648 introduced a `snapshot_directory` configuration option that redirected snapshots from the data directory to a user-specified external directory. The approach was straightforward:

1. Add `snapshot_directory` to `cassandra.yaml`
2. Modify `Directories.java` to redirect snapshot paths when configured
3. Use file copies instead of hardlinks (since the external dir may be on a different filesystem)

This worked for the basic case but was incomplete for production use.

---

## 3. Community Discussion — What Was Missing

The Apache mailing list thread "[DISCUSS] Snapshots outside of Cassandra data directory" (January–February 2025) identified the following gaps:

### Gap 1: No SSTable Deduplication

**Raised by**: Štefan Miklošovič  
**Issue**: If you take snapshot A, then snapshot B a minute later, both snapshots may reference many of the same SSTables. With file copies, every SSTable is copied to every snapshot directory — potentially **doubling or tripling** storage consumption.  
**Impact**: The feature designed to save disk space could paradoxically *waste* more space than hardlinks.

### Gap 2: Unsafe Deletion of Shared SSTables

**Raised by**: Štefan Miklošovič, Ekaterina Dimitrova  
**Issue**: If snapshot A and B share SSTable X, and you delete snapshot A, the files for SSTable X are deleted. Snapshot B is now corrupted — it references files that no longer exist.  
**Impact**: Data loss / corrupted backups.

### Gap 3: No Hierarchical Directory Structure

**Raised by**: Multiple participants  
**Issue**: All nodes would dump snapshots into the same flat directory if pointed at a shared NFS mount. No way to distinguish which node produced which snapshot.  
**Impact**: Multi-node restores become impossible. Naming collisions between nodes.

### Gap 4: Missing Token/Topology Information in Manifests

**Raised by**: Štefan Miklošovič  
**Issue**: Standard snapshot manifests only record file names. For restoring to a different cluster or performing point-in-time recovery, you need to know: which token ranges the node owned, the schema at snapshot time, and the node's identity.  
**Impact**: External restore tooling must guess or separately track this metadata.

### Gap 5: No Bandwidth Control for Copy I/O

**Raised by**: ML discussion  
**Issue**: Copying large SSTables (10s–100s of GB) to an external mount can saturate disk I/O on the source volume, degrading read/write latency for live queries.  
**Impact**: Taking a snapshot becomes a disruptive operation in production.

### Gap 6: All Snapshot Types Were Redirected

**Raised by**: Ekaterina Dimitrova, Jacek Lewandowski  
**Issue**: The original PR redirected *all* snapshots — including diagnostic snapshots (pre-truncate, pre-drop, repair), ephemeral snapshots, and system table snapshots. These are short-lived, local-only by design, and should not be copied externally.  
**Impact**: Unnecessary I/O, wasted external storage, potential breakage of repair/truncate workflows.

### Gap 7: No Incremental Backup Support

**Raised by**: ML discussion  
**Issue**: Cassandra's incremental backup feature (`incremental_backups: true`) creates hardlinks in a `/backups/` subdirectory. This was not integrated with the external snapshot directory.  
**Impact**: Operators wanting all backup data on the external mount still had incremental backups on the data disk.

### Gap 8: SnapshotLoader Coupling

**Raised by**: Code review  
**Issue**: The SnapshotLoader was patched with `addSnapshotDirectory()` to scan the external directory for snapshots on startup. This was fragile — a constructor hack that violated the original API contract.  
**Impact**: Regressions in snapshot enumeration, confusing code.

### Gap 9: No Nodetool Visibility

**Raised by**: Multiple participants  
**Issue**: No way to list or manage external snapshots via nodetool. Operators would need to manually browse the external directory.  
**Impact**: Poor operability in production.

### Gap 10: Directories.java Overloaded with External Logic

**Raised by**: Architectural review  
**Issue**: `Directories.java` is a critical path class. Adding external directory redirect logic with `Optional<File>` returns and null-checked paths made the entire CFS read/write path fragile.  
**Impact**: Risk of regressions in core data path operations.

---

## 4. Why the Gaps Existed in PR #4648

The original PR was a pragmatic, minimal approach that solved the immediate problem ("snapshots should not be on the data disk"). The gaps existed because:

| Gap | Root Cause |
|---|---|
| **No deduplication** | The PR treated snapshots as independent directories. The concept of sharing SSTables *between* snapshots was out of scope for the initial implementation. |
| **Unsafe deletion** | Without deduplication, there's no shared state — so deletion just deletes the directory. Sharing was implicit (via hardlinks in the original model) but not modeled explicitly for copies. |
| **Flat directory** | The PR assumed a single-node perspective. Multi-node shared storage (NFS, EFS) was not considered. |
| **Simple manifests** | Reused existing `SnapshotManifest` which was designed for local use (file list + TTL). No need for restoration metadata when using local hardlinks. |
| **No throttling** | Hardlinks are instantaneous. The shift to file copies introduced I/O cost that wasn't present before. |
| **All snapshots redirected** | The PR modified `Directories.java` at a low level, which is called for all snapshot types. Type-aware gating requires knowledge of the caller's intent, which isn't available at the Directories layer. |
| **No backup integration** | Separate feature, separate code path — reasonable to defer. |
| **SnapshotLoader hack** | The simplest way to make external snapshots visible on restart without redesigning the loading pipeline. |
| **No nodetool** | Visibility features are typically added after the core mechanism works. |
| **Directories.java bloat** | The natural place to change path resolution is Directories.java, but the external logic requires too much context (snapshot type, dedup state, manifests). |

These are all reasonable trade-offs for an initial PR. The mailing list discussion elevated the design to production-grade.

---

## 5. High-Level Design (HLD)

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         nodetool snapshot                       │
│                    nodetool listexternalsnapshots                │
│                    nodetool listbackups / clearbackups           │
└────────────┬──────────────────────────────┬─────────────────────┘
             │                              │
             ▼                              ▼
┌──────────────────────┐       ┌──────────────────────────────────┐
│  ColumnFamilyStore   │       │     NodeTool Commands            │
│                      │       │  - ListExternalSnapshots         │
│  snapshotWithout-    │       │  - ListBackups                   │
│    Memtable()        │       │  - ClearBackups                  │
│                      │       └─────────┬────────────────────────┘
│  Decision Point:     │                 │
│  shouldStoreExtern-  │                 │
│    ally() ?          │                 │
│    ┌─────┴─────┐     │                 │
│    │Yes        │No   │                 │
│    ▼           ▼     │                 │
│ External    Local    │                 │
│ Snapshot   Hardlink  │                 │
│ Path       Path      │                 │
└────┬───────────┬─────┘                 │
     │           │                       │
     ▼           ▼                       ▼
┌──────────────────────┐       ┌─────────────────────────────────┐
│ ExternalSnapshot-    │       │       ExternalSnapshot-          │
│    Manager           │◄──────│          Manager                 │
│                      │       │       (listing/clearing)         │
│ - copySSTablesFor-   │       └─────────────────────────────────┘
│     Snapshot()       │
│ - writeManifest()    │
│ - clearSnapshot()    │
│ - collectReferenced- │
│     SSTableIds()     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│                    External Storage (snapshot_directory)         │
│                                                                  │
│  <root>/<cluster>/<dc>/<host_id>/                               │
│    data/                                                         │
│      <keyspace>/                                                 │
│        <table-uuid>/                                             │
│          sstables/     ← deduplicated flat pool                  │
│          manifests/    ← per-tag JSON manifests                  │
│    backups/                                                      │
│      <keyspace>/                                                 │
│        <table-uuid>/                                             │
│          sstables/     ← incremental backup SSTables             │
└──────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| **Separate `ExternalSnapshotManager` class** | Isolates all external logic from `Directories.java`. The core data path is untouched. |
| **Decision at CFS level, not Directories level** | `ColumnFamilyStore.snapshotWithoutMemtable()` has full context: snapshot name, ephemeral flag, keyspace. This enables type-aware gating. |
| **UUID-based SSTable deduplication** | Cassandra 4.1+ supports `uuid_sstable_identifiers_enabled`. UUIDs are globally unique, making dedup safe without hashing file contents. |
| **Manifest-based reference counting** | Each manifest lists the SSTable IDs it uses. On deletion, scan remaining manifests. Simple, atomic, no external index. |
| **Singleton pattern for manager** | One manager per node. Thread-safe via ConcurrentHashMap where needed. |
| **Local manifest + schema for compatibility** | Even for external snapshots, we write a local `manifest.json` so `nodetool listsnapshots` works. |

### Component Interaction Flow

**Taking a snapshot:**
1. `ColumnFamilyStore.snapshotWithoutMemtable()` is called
2. `ExternalSnapshotManager.shouldStoreExternally()` evaluates: enabled? user snapshot? non-system keyspace?
3. If external: collect all SSTableReaders, call `copySSTablesForSnapshot()` (with dedup checking)
4. Write enhanced `ExternalSnapshotManifest` with tokens, schema, host_id
5. Write local manifest + schema for `listsnapshots` compatibility
6. Register snapshot with `StorageService`

**Clearing a snapshot:**
1. `ColumnFamilyStore.clearSnapshot()` calls `Directories.clearSnapshot()` (local) AND `ExternalSnapshotManager.clearSnapshot()` (external)
2. `ExternalSnapshotManager.clearSnapshot()` reads the manifest, deletes it
3. For each SSTable ID in the deleted manifest, scans remaining manifests
4. Only deletes SSTable files that have zero remaining references

---

## 6. System Design — Detailed Architecture

### 6.1 ExternalSnapshotManifest

Enhanced JSON manifest stored per snapshot tag per table:

```json
{
  "files": ["nb-1-big-Data.db", "nb-1-big-Index.db", ...],
  "sstable_ids": ["a1b2c3d4e5f6...", "f6e5d4c3b2a1..."],
  "created_at": "2026-03-22T10:30:00Z",
  "expires_at": "2026-03-29T10:30:00Z",
  "tokens": ["-9223372036854775808", "0", "9223372036854775807"],
  "schema_version": "e4a68a30-d8e1-11e5-a7ed-93ac1f3a5e47",
  "schema_cql": "CREATE TABLE ks.my_table (\n  id uuid PRIMARY KEY,\n  data text\n) ...",
  "keyspace": "my_keyspace",
  "table": "my_table",
  "host_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

**Forward/backward compatibility**: `@JsonIgnoreProperties(ignoreUnknown = true)` ensures older readers can parse manifests written by newer versions.

### 6.2 ExternalSnapshotManager

Singleton service managing all external snapshot operations:

| Method | Purpose |
|---|---|
| `isEnabled()` | Checks `snapshot_directory` + `uuid_sstable_identifiers_enabled` |
| `shouldStoreExternally(name, ephemeral, ks)` | Gating: only user snapshots for non-system keyspaces |
| `getNodeBaseDir()` | Resolves `<root>/<cluster>/<dc>/<host_id>` |
| `copySSTablesForSnapshot(sstables, ks, table, id, limiter)` | Copy with dedup + optional bandwidth throttling |
| `writeManifest(tag, ks, table, id, files, ids, ttl, time, cql, ver)` | Write enhanced manifest |
| `clearSnapshot(tag, ks, table, id)` | Reference-counted deletion |
| `clearAllSnapshots(ks, table, id)` | Delete all manifests + unreferenced SSTables |
| `collectReferencedSSTableIds(ks, table, id)` | Scan manifests → union of SSTable IDs |
| `copySSTableForIncrementalBackup(ssTable, ks, table, id)` | Copy to backups pool |
| `listAllExternalSnapshots()` | Walk directory tree → Map<tag, List<manifest>> |
| `listIncrementalBackups() / listIncrementalBackups(ks, table, id)` | List backup files |
| `clearIncrementalBackups(ks, table, id, olderThan)` | Age-based backup cleanup |
| `clearIncrementalBackups(ks, table)` | Filter-based backup cleanup |
| `computeExternalSnapshotSize(ks, table, id)` | Pool directory size |
| `sanitizePath(component)` | Safe directory names |

### 6.3 Snapshot Gating Logic

```
shouldStoreExternally(snapshotName, ephemeral, keyspace):
  ├── isEnabled()? ─── NO ──→ return false (local hardlinks)
  ├── ephemeral? ───── YES ─→ return false (cleared on restart)
  ├── system keyspace? YES ─→ return false (system_schema, system, etc.)
  ├── prefix "pre-"? ─ YES ─→ return false (pre-truncate diagnostic)
  ├── prefix "repair-"? YES → return false (repair snapshot)
  ├── prefix "truncated-"? ── return false (truncation diagnostic)
  ├── prefix "dropped-"? ──── return false (drop diagnostic)
  └── else ────────────────── return true (user snapshot → external)
```

### 6.4 Reference-Counted Cleanup Algorithm

```
clearSnapshot(tag, keyspace, tableName, tableId):
  1. Read manifest file: <manifests>/<tag>.json
  2. Delete the manifest file
  3. sstableIdsToCheck = manifest.sstable_ids
  4. referencedIds = {} (empty set)
  5. For each remaining manifest in <manifests>/:
       referencedIds.addAll(manifest.sstable_ids)
  6. For each id in sstableIdsToCheck:
       if id NOT IN referencedIds:
         delete all files matching "<id>-*" from sstables/ pool
       else:
         keep (still referenced)
```

**Correctness guarantee**: The manifest is deleted *before* scanning remaining manifests. This ensures the deleted snapshot's IDs are not counted as "still referenced" by themselves.

### 6.5 Integration Points

```
ColumnFamilyStore.snapshotWithoutMemtable()
  └── ExternalSnapshotManager.shouldStoreExternally()
  └── ExternalSnapshotManager.copySSTablesForSnapshot()
  └── ExternalSnapshotManager.writeManifest()

ColumnFamilyStore.clearSnapshot()
  ├── Directories.clearSnapshot()               [local hardlinks]
  └── ExternalSnapshotManager.clearSnapshot()    [external storage]

Keyspace.clearSnapshot()
  ├── CFS.clearSnapshot() for each CFS          [per-table]
  └── ExternalSnapshotManager.clearAllSnapshots() [if tag=null]

SnapshotManager.clearSnapshot(TableSnapshot)     [TTL expiry path]
  ├── Directories.removeSnapshotDirectory()      [local]
  └── ExternalSnapshotManager.clearSnapshot()    [external]
```

---

## 7. Configuration Reference

### cassandra.yaml

```yaml
# Optional: Redirect user snapshot storage to a separate mount point.
# Requires uuid_sstable_identifiers_enabled: true
# Only user-initiated snapshots are redirected; system/diagnostic snapshots remain local.
snapshot_directory: /mnt/snapshots

# Bandwidth limit for SSTable copies to snapshot_directory (bytes/sec).
# 0 = unlimited. Recommended for production to avoid I/O saturation.
snapshot_copy_bytes_per_second: 52428800   # 50 MB/s

# Copy incremental backups to snapshot_directory/backups/ as well.
# Requires snapshot_directory + uuid_sstable_identifiers_enabled.
external_incremental_backups: false

# REQUIRED for external snapshots:
uuid_sstable_identifiers_enabled: true
```

### Validation Rules

| Configuration | Validation |
|---|---|
| `snapshot_directory` | Must be a valid path; checked at startup |
| `uuid_sstable_identifiers_enabled` | Must be `true` when `snapshot_directory` is set; warning logged if not |
| `snapshot_copy_bytes_per_second` | Must be ≥ 0; validated at startup |
| `external_incremental_backups` | Only effective when `snapshot_directory` is set |

---

## 8. Directory Layout

### Full Example

```
/mnt/snapshots/                                    ← snapshot_directory
  my_cluster/                                      ← cluster_name (sanitized)
    datacenter1/                                   ← DC name from snitch
      a1b2c3d4-e5f6-7890-abcd-ef1234567890/       ← node host_id
        data/
          my_keyspace/
            users-abc123def456.../                  ← table_name-table_id
              sstables/                             ← flat deduplicated pool
                aaaa1111-...-Data.db
                aaaa1111-...-Index.db
                aaaa1111-...-Filter.db
                bbbb2222-...-Data.db
                bbbb2222-...-Index.db
              manifests/
                daily_backup.json                   ← snapshot tag → manifest
                weekly_backup.json
            orders-def456abc789.../
              sstables/
                ...
              manifests/
                ...
        backups/                                    ← if external_incremental_backups=true
          my_keyspace/
            users-abc123def456.../
              sstables/
                cccc3333-...-Data.db
                ...
```

### Design Rationale for Hierarchy

- **Cluster** → **DC** → **Host ID**: Enables multiple clusters/DCs to share one NFS mount without collision
- **Host ID (UUID)** instead of hostname: Immutable identifier, safe across hostname changes
- **Flat SSTable pool per table**: Maximizes deduplication; all snapshots of a table share one pool
- **Separate manifests directory**: Clean separation of metadata vs. data; easy manifest enumeration

---

## 9. Deduplication & Reference-Counted Cleanup

### How Deduplication Works

1. Cassandra 4.1+ can assign UUID-based identifiers to SSTables (`uuid_sstable_identifiers_enabled: true`)
2. Each SSTable has a globally unique UUID (e.g., `aaaa1111-bbbb-cccc-dddd-eeee2222ffff`)
3. When copying an SSTable to the external pool, we check: `<pool>/<sstable_id>-Data.db` exists?
4. If yes → skip (already deduplicated). If no → copy all components.

**Storage savings example:**
```
Snapshot A: references SSTables {X, Y, Z}     → copies X, Y, Z
Snapshot B: references SSTables {X, Y, W}     → copies only W (X, Y already exist)
Snapshot C: references SSTables {X, V}         → copies only V

Pool contains: X, Y, Z, W, V  (5 SSTables instead of 9 without dedup)
```

### How Reference-Counted Cleanup Works

```
State: Pool has {X, Y, Z, W, V}
       Manifest A references {X, Y, Z}
       Manifest B references {X, Y, W}
       Manifest C references {X, V}

Delete Snapshot A:
  1. Remove manifest A
  2. Check A's IDs: {X, Y, Z}
  3. Remaining manifests reference: B→{X,Y,W}, C→{X,V}
     Union = {X, Y, W, V}
  4. X ∈ union → keep
     Y ∈ union → keep
     Z ∉ union → DELETE
  5. Pool now: {X, Y, W, V}

Delete Snapshot B:
  1. Remove manifest B
  2. Check B's IDs: {X, Y, W}
  3. Remaining manifests reference: C→{X,V}
     Union = {X, V}
  4. X ∈ union → keep
     Y ∉ union → DELETE
     W ∉ union → DELETE
  5. Pool now: {X, V}

Delete Snapshot C:
  1. Remove manifest C
  2. Check C's IDs: {X, V}
  3. No remaining manifests. Union = {}
  4. X ∉ union → DELETE
     V ∉ union → DELETE
  5. Pool now: {} (empty)
```

---

## 10. Nodetool Commands

### `nodetool listexternalsnapshots`

Lists all external snapshots with deduplication metadata.

```
$ nodetool listexternalsnapshots

External Snapshot Details:
Directory: /mnt/snapshots

Snapshot Tag    Keyspace      Table    SSTable IDs  Files  Created At                Expires At  Host ID
daily_backup    my_keyspace   users    12           15     2026-03-22T10:30:00Z      never       a1b2c3d4-...
weekly_backup   my_keyspace   users    8            10     2026-03-15T02:00:00Z      never       a1b2c3d4-...
daily_backup    my_keyspace   orders   5            7      2026-03-22T10:30:00Z      never       a1b2c3d4-...
```

### `nodetool listbackups`

Lists incremental backup files in external storage.

```
$ nodetool listbackups
$ nodetool listbackups -k my_keyspace       # filter by keyspace
```

### `nodetool clearbackups`

Clears incremental backup files from external storage.

```
$ nodetool clearbackups                                # clear all
$ nodetool clearbackups -k my_keyspace                 # clear by keyspace
$ nodetool clearbackups -k my_keyspace -t users        # clear specific table
```

---

## 11. Files Changed — Complete Inventory

### New Files Created (7)

| File | Purpose |
|---|---|
| `src/java/.../service/snapshot/ExternalSnapshotManifest.java` | Enhanced JSON manifest with tokens, schema, SSTable UUIDs, host_id |
| `src/java/.../service/snapshot/ExternalSnapshotManager.java` | Central manager: dedup, ref-counting, hierarchy, backup, listing |
| `src/java/.../tools/nodetool/ListExternalSnapshots.java` | `nodetool listexternalsnapshots` |
| `src/java/.../tools/nodetool/ListBackups.java` | `nodetool listbackups` |
| `src/java/.../tools/nodetool/ClearBackups.java` | `nodetool clearbackups` |
| `test/unit/.../service/snapshot/ExternalSnapshotManifestTest.java` | 7 unit tests for manifest serialization, TTL, expiry |
| `test/unit/.../service/snapshot/ExternalSnapshotManagerTest.java` | 8 unit tests for dedup, ref-counting, gating, listing |

### Existing Files Modified (9)

| File | Changes |
|---|---|
| `src/java/.../config/Config.java` | Added `snapshot_copy_bytes_per_second`, `external_incremental_backups` fields |
| `src/java/.../config/DatabaseDescriptor.java` | Validation logic, 5 new accessor methods |
| `src/java/.../db/ColumnFamilyStore.java` | External snapshot routing in `snapshotWithoutMemtable()`, new `createExternalSnapshot()`, external cleanup in `clearSnapshot()` |
| `src/java/.../db/Directories.java` | Simplified: removed external directory redirect logic |
| `src/java/.../db/Keyspace.java` | `clearSnapshot()` now clears external storage too |
| `src/java/.../service/snapshot/SnapshotLoader.java` | Removed `addSnapshotDirectory()` hack, simplified constructor |
| `src/java/.../service/snapshot/SnapshotManager.java` | TTL-expired snapshot cleanup now clears external storage |
| `src/java/.../tools/NodeTool.java` | Registered 3 new commands |
| `conf/cassandra.yaml` | Updated docs, added 2 new config options |

---

## 12. What Changed and Why — Detailed Changelog

### Config.java

**What**: Added two new configuration fields:

```java
public volatile long snapshot_copy_bytes_per_second = 0;
public boolean external_incremental_backups = false;
```

**Why**: `snapshot_copy_bytes_per_second` addresses **Gap 5** (bandwidth control). `external_incremental_backups` addresses **Gap 7** (incremental backup support). Both are opt-in with safe defaults.

---

### DatabaseDescriptor.java

**What**: Added validation during daemon initialization and 5 new accessor methods:

- `isExternalSnapshotEnabled()` — true when `snapshot_directory` is set AND UUIDs are enabled
- `getSnapshotCopyBytesPerSecond()` / `setSnapshotCopyBytesPerSecond(long)` — bandwidth limit
- `isExternalIncrementalBackupsEnabled()` — gated on both config flags
- Enhanced UUID validation that logs a warning if `snapshot_directory` is set but UUIDs are disabled

**Why**: Centralizes all validation in one place. Prevents silent misconfiguration.

---

### ColumnFamilyStore.java

**What**: 
1. `snapshotWithoutMemtable()` now calls `ExternalSnapshotManager.shouldStoreExternally()` to decide the path
2. New `createExternalSnapshot()` method that uses `ExternalSnapshotManager` for copy + manifest + schema
3. `clearSnapshot()` now calls both `Directories.clearSnapshot()` (local) AND `ExternalSnapshotManager.clearSnapshot()` (external)

**Why**: This is **the** key integration point. Moving the decision to CFS level (instead of Directories) addresses **Gap 6** (only user snapshots are redirected) and **Gap 10** (Directories.java stays clean). The dual cleanup in `clearSnapshot()` ensures both local markers and external data are removed.

---

### Directories.java

**What**: Simplified `getSnapshotBaseDirectory()`, `getSnapshotDirectory()`, `getSnapshotSearchPaths()`, and `clearSnapshot()` by removing all external directory redirect logic.

**Why**: Addresses **Gap 10**. Directories.java is on the critical path for all reads/writes. External snapshot logic doesn't belong here — it requires context (snapshot type, dedup state) that Directories doesn't have.

---

### Keyspace.java

**What**: `clearSnapshot()` now iterates CFS instances and calls `ExternalSnapshotManager.clearSnapshot()` / `clearAllSnapshots()`.

**Why**: When `nodetool clearsnapshot` is called at the keyspace level (not CFS level), external storage must also be cleaned. Without this, external snapshots would leak.

---

### SnapshotLoader.java

**What**: Removed the `addSnapshotDirectory()` method. Simplified constructor to `this(DatabaseDescriptor.getAllDataFileLocations())`.

**Why**: Addresses **Gap 8**. The `addSnapshotDirectory()` was a hack to inject the external directory into the loader's search paths. External snapshots now have their own listing mechanism (`ExternalSnapshotManager.listAllExternalSnapshots()`).

---

### SnapshotManager.java

**What**: `clearSnapshot(TableSnapshot)` now also calls `ExternalSnapshotManager.clearSnapshot()` for the external storage copy, extracting the table ID from the snapshot ID format `"$ks:$table_name:$table_id:$tag"`.

**Why**: Snapshots with TTL are cleared by `SnapshotManager` when they expire. Without this change, expired snapshots would leave orphaned files in external storage.

---

### NodeTool.java

**What**: Registered `ClearBackups.class`, `ListBackups.class`, `ListExternalSnapshots.class` in the command list.

**Why**: Addresses **Gap 9** (nodetool visibility).

---

### cassandra.yaml

**What**: Updated `snapshot_directory` comment block with hierarchical layout documentation, UUID requirement. Added `snapshot_copy_bytes_per_second` and `external_incremental_backups` entries.

**Why**: Production operators need clear documentation of the feature's behavior and requirements directly in the config file.

---

## 13. Test Coverage

### New Tests (15 total)

**ExternalSnapshotManifestTest** (7 tests):

| Test | Validates |
|---|---|
| `testSerializeAndDeserialize` | Round-trip JSON with all fields |
| `testSerializeWithTTL` | TTL → `expires_at` calculation |
| `testIsExpired` | Expiry checking logic |
| `testNoTTLNeverExpires` | Null TTL never expires |
| `testDeserializeFromInvalidFile` | Graceful error on corrupt JSON |
| `testDeserializeIgnoresUnknownFields` | Forward compatibility |
| `testEqualsAndHashCode` | Object identity |

**ExternalSnapshotManagerTest** (8 tests):

| Test | Validates |
|---|---|
| `testSanitizePath` | Path component sanitization |
| `testShouldStoreExternallyFiltersSystemKeyspaces` | System keyspace exclusion |
| `testShouldStoreExternallyFiltersEphemeral` | Ephemeral snapshot exclusion |
| `testShouldStoreExternallyFiltersDiagnosticPrefixes` | pre-/repair-/truncated-/dropped- exclusion |
| `testCollectReferencedSSTableIds` | Manifest scanning for reference counting |
| `testClearIncrementalBackupsFromDirectory` | Age-based backup cleanup |
| `testReferenceCountedDeletion` | Full dedup + ref-counted cleanup cycle |
| `testManifestListingFromDirectoryStructure` | Directory tree walking for listing |

### Regression Tests (74 tests, 0 failures)

| Test Class | Tests | Result |
|---|---|---|
| SnapshotManifestTest | 5 | ✅ PASS |
| SnapshotLoaderTest | 6 | ✅ PASS |
| SnapshotManagerTest | 4 | ✅ PASS |
| TableSnapshotTest | 7 | ✅ PASS |
| DirectoriesTest | 38 | ✅ PASS |
| ColumnFamilyStoreTest | 14 | ✅ PASS |

---

## 14. Live Testing Results & Runtime Bugs Discovered

### Test Environment

| Component | Detail |
|---|---|
| **OS** | WSL Ubuntu 20.04 on Windows |
| **Java** | OpenJDK 11.0.27 |
| **Cassandra** | 4.1.11-SNAPSHOT (built from source with `ant jar`) |
| **Config** | `snapshot_directory: /tmp/cassandra-test/snapshots`, `uuid_sstable_identifiers_enabled: true` |

### Tests Executed

| Step | Command | Result |
|---|---|---|
| 1 | Create keyspace/table, insert 3 rows, flush | Data on disk |
| 2 | `nodetool snapshot -t test_snap_1 test_ks` | Snapshot created, manifest + 8 SSTable files copied to external dir |
| 3 | `nodetool snapshot -t test_snap_2 test_ks` | Second snapshot created, manifest written, SSTables **deduplicated** (ref count = 2) |
| 4 | `nodetool listsnapshots` | Shows both snapshots with sizes |
| 5 | `nodetool listexternalsnapshots` | Shows both external snapshots with host IDs, dedup counts, timestamps |
| 6 | `nodetool listbackups` | Correctly reports "No incremental backups found" |
| 7 | `nodetool clearsnapshot -t test_snap_1 test_ks` | Manifest removed, SSTables **retained** (still referenced by snap_2) |
| 8 | `nodetool clearsnapshot -t test_snap_2 test_ks` | Manifest + all SSTables removed (ref count reached 0) |

**All deduplication and ref-counted cleanup behaviors verified end-to-end.**

### Bug #1: NPE in nodetool Client JVM

**Symptom**: `nodetool listexternalsnapshots` crashed with `NullPointerException`.

**Root Cause**: nodetool commands run in a **separate JVM** from the Cassandra daemon. The `DatabaseDescriptor.conf` field is `null` in client-mode JVMs because `daemonInitialization()` has not been called. Methods `hasSnapshotDirectory()` and `getSnapshotDirectory()` dereferenced `conf` without null checks.

**Fix**:
- Made `DatabaseDescriptor.hasSnapshotDirectory()` null-safe: `return conf != null && conf.snapshot_directory != null && !conf.snapshot_directory.isEmpty();`
- Made `DatabaseDescriptor.getSnapshotDirectory()` null-safe: `return conf != null ? conf.snapshot_directory : null;`
- Added `DatabaseDescriptor.toolInitialization(false)` at the start of all 3 custom nodetool commands (`ListExternalSnapshots`, `ListBackups`, `ClearBackups`)

### Bug #2: Empty Results Due to StorageService Unavailability

**Symptom**: `nodetool listexternalsnapshots` returned "No external snapshots found" despite files existing on disk.

**Root Cause**: `listAllExternalSnapshots()` called `getNodeBaseDir()` which uses `StorageService.instance.getLocalHostId()`. In the nodetool client JVM, `StorageService` is not initialized, so the host ID resolved to `"unknown"`, producing a path like `.../unknown/data/...` that doesn't match any files.

**Fix**: Added a fallback `listAllExternalSnapshotsFromRoot()` method that scans the entire snapshot root directory tree instead of relying on a specific node path. When `getNodeBaseDir()` fails or returns a path containing "/unknown", the system automatically falls back to root-level scanning with the directory pattern: `<root>/<cluster>/<dc>/<host_id>/data/<ks>/<table>/manifests/<tag>.json`.

### Why These Bugs Weren't Caught Earlier

Both bugs are **client-JVM-specific** — they only manifest when running nodetool (a separate JMX client process), not during server-side snapshot operations or unit tests. The existing tests call `ExternalSnapshotManager` methods directly within a test JVM where `DatabaseDescriptor.daemonInitialization()` is called in `@BeforeClass`, so `conf` is always populated and `StorageService` is available.

**Lesson learned**: Custom nodetool commands that read the local filesystem (not just JMX) need `toolInitialization()` and must handle the absence of server-side singletons like `StorageService`.

---

## 15. 3-Node Cluster Disaster Recovery & Restore Test

### Objective

Validate end-to-end disaster recovery: create a 3-node cluster, populate data, take external snapshots, **destroy all data**, then restore entirely from external snapshot files using `sstableloader`.

### Test Environment

| Component | Details |
|---|---|
| Platform | WSL2 Ubuntu-20.04, Windows |
| Java | OpenJDK 11.0.27 |
| Cassandra | 4.1.11-SNAPSHOT (built from workspace) |
| Cluster | 3 nodes on 127.0.0.1-3, ports 9042-9044, JMX 7199-7201 |
| Replication | SimpleStrategy, RF=3 |
| External Snapshots | `/tmp/ext_snapshots` (separate from data dirs) |
| UUID SSTables | `uuid_sstable_identifiers_enabled: true` |

### Test Phases & Results

| Phase | Action | Result |
|---|---|---|
| 1. Setup | Generate per-node configs (YAML, JVM opts, JMX ports) | 3 node configs created |
| 2. Start Cluster | Start all 3 nodes, verify UN status | All 3 nodes UN |
| 3. Create Data & Snapshot | Insert 20 rows (RF=3), flush, `nodetool snapshot -t restore_snap` | 20 rows on all nodes, 6 .db + 1 manifest per host in external dir |
| 4. Disaster & Restore | Stop cluster, **WIPE all data/commitlog/hints**, restart empty, recreate schema, `sstableloader` from external snapshots | All 3 hosts' SSTables loaded successfully |
| 5. Verify | Row counts, data comparison, spot checks | **20 rows on all 3 nodes, ALL DATA ROWS MATCH** |

### Bug #3: SSTable Filename Format in External Snapshots

**Discovered during**: Phase 4 restore — `sstableloader` reported "Unknown directory" (exit code 1) or silently loaded 0 SSTables.

**Root Cause**: `ExternalSnapshotManager.copySSTablesForSnapshot()` created filenames using only `<sstable_id>-<component>` (e.g., `3gyx_0nru...-Data.db`), stripping the version and format parts. Cassandra's `Descriptor.fromFilenameWithComponent()` expects 4 hyphen-separated tokens: `<version>-<id>-<format>-<component>` (e.g., `na-3gyx_0nru...-big-Data.db`). With only 2 tokens, all SSTable tools (`sstableloader`, `upgradesstables`, etc.) failed to recognize the files.

**Fix**:
- Changed `copySSTablesForSnapshot()` to use `sourceFile.name()` (the original Cassandra filename) instead of constructing a stripped name
- Changed `deleteSSTableFromPool()` to use `f.name().contains(sstableId)` instead of `f.name().startsWith(sstableId + "-")` since the id is now in the middle of the filename
- Applied same fix to `copySSTableForIncrementalBackup()`
- Deduplication still works because identical SSTables produce identical filenames

**Impact**: Without this fix, external snapshots cannot be used with any Cassandra SSTable tool for restoration.

### Restore Approach: sstableloader

The successful restore used `sstableloader`, which:
1. Reads SSTables from a staging directory (schema from Statistics.db)
2. Connects to the cluster via native CQL protocol for ring discovery
3. Streams data to the correct replica nodes based on token ranges
4. Handles schema differences transparently (new table UUIDs, column IDs)

Cold-copy approaches (placing SSTables directly in data directories) fail because `CREATE TABLE ... WITH ID = <uuid>` preserves the table-level UUID but not internal column serialization IDs. The SSTable's serialization header becomes incompatible with the recreated schema.

### Full Test Output (abridged)

```
Phase 1: Creating 3-Node Cluster Configuration         ✓
Phase 2: Starting 3-Node Cassandra Cluster              ✓ (3 nodes UN)
Phase 3: Create Data & Take Snapshots                   ✓ (20 rows, 6 .db + 1 manifest per host)
Phase 4: Disaster Simulation & Restore (sstableloader)  ✓
  - Node 1: sstableloader OK
  - Node 2: sstableloader OK
  - Node 3: sstableloader OK
Phase 5: VERIFYING RESTORED DATA
  - Node 1: 20 rows [OK]
  - Node 2: 20 rows [OK]
  - Node 3: 20 rows [OK]
  - ALL 20 DATA ROWS MATCH!
  - Spot checks: id=1 FOUND, id=10 FOUND, id=20 FOUND
  RESTORE TEST: SUCCESS
```

---

## 16. Future Considerations

| Area | Notes |
|---|---|
| **Distributed snapshot coordination** | The current design is per-node. A future CEP could coordinate cluster-wide consistent snapshots with a single manifest. |
| **Remote storage backends** | The current implementation uses local/NFS file copies. A pluggable `SnapshotStorageProvider` interface could support S3/GCS/Azure Blob directly. |
| **Manifest indexing** | For very large numbers of snapshots, scanning all manifests for reference counting could become slow. An index file could optimize this. |
| **Snapshot restore tooling** | The enhanced manifests (tokens, schema) enable automated restore. A `nodetool restoresnapshot` command could be built on top. |
| **Compaction-aware dedup** | After a compaction replaces SSTables, new snapshots reference new IDs. Old IDs may only be referenced by one old snapshot. A background task could detect and warn. |
| **Metrics** | JMX metrics for external snapshot size, copy throughput, and dedup ratio would aid monitoring. |

---

*End of Design Document*
