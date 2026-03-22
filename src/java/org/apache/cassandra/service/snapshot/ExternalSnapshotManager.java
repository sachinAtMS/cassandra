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

package org.apache.cassandra.service.snapshot;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import com.google.common.annotations.VisibleForTesting;
import com.google.common.util.concurrent.RateLimiter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.config.DurationSpec;
import org.apache.cassandra.io.FSWriteError;
import org.apache.cassandra.io.sstable.Component;
import org.apache.cassandra.io.sstable.Descriptor;
import org.apache.cassandra.io.sstable.SSTableId;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.io.util.FileUtils;
import org.apache.cassandra.locator.IEndpointSnitch;
import org.apache.cassandra.service.StorageService;

/**
 * Manages external snapshot storage with deduplication and reference-counted cleanup.
 *
 * <h3>Directory Structure</h3>
 * <pre>
 * &lt;snapshot_root_dir&gt;/
 *   &lt;cluster_name&gt;/
 *     &lt;datacenter&gt;/
 *       &lt;node_host_id&gt;/
 *         data/
 *           &lt;keyspace&gt;/
 *             &lt;table_name&gt;-&lt;table_id&gt;/
 *               sstables/          ← flat SSTable pool (deduplicated by UUID id)
 *               manifests/
 *                 &lt;snapshot_tag&gt;.json   ← ExternalSnapshotManifest
 *         backups/
 *           &lt;keyspace&gt;/
 *             &lt;table_name&gt;-&lt;table_id&gt;/
 *               sstables/          ← incremental backup SSTables
 *               manifests/
 *                 backup_&lt;timestamp&gt;.json
 * </pre>
 *
 * <h3>Deduplication</h3>
 * SSTables are stored in a flat pool directory per table. Each SSTable is identified by its
 * UUID-based identifier (requires {@code uuid_sstable_identifiers_enabled: true}). Before
 * copying an SSTable, we check if it already exists in the pool. Multiple snapshot manifests
 * can reference the same SSTable without duplicating storage.
 *
 * <h3>Reference-Counted Cleanup</h3>
 * When a snapshot is cleared, its manifest is removed. Then, for each SSTable referenced by
 * that manifest, we scan all remaining manifests for the same table. If no other manifest
 * references the SSTable, it is physically deleted. This prevents data loss from shared SSTables.
 *
 * <h3>User Snapshots Only</h3>
 * Only user-initiated snapshots (via nodetool snapshot) are stored externally. Diagnostic
 * snapshots, repair snapshots, ephemeral snapshots, and system table snapshots continue
 * to use hardlinks in the data directory.
 */
public class ExternalSnapshotManager
{
    private static final Logger logger = LoggerFactory.getLogger(ExternalSnapshotManager.class);

    public static final String DATA_SUBDIR = "data";
    public static final String BACKUPS_SUBDIR = "backups";
    public static final String SSTABLES_SUBDIR = "sstables";
    public static final String MANIFESTS_SUBDIR = "manifests";
    public static final String MANIFEST_EXT = ".json";

    private static final ExternalSnapshotManager instance = new ExternalSnapshotManager();

    public static ExternalSnapshotManager instance()
    {
        return instance;
    }

    /**
     * Returns true if external snapshot storage is enabled and properly configured.
     * Requires both snapshot_root_dir to be set AND uuid_sstable_identifiers_enabled.
     */
    public static boolean isEnabled()
    {
        return DatabaseDescriptor.hasSnapshotDirectory()
               && DatabaseDescriptor.isUUIDSSTableIdentifiersEnabled();
    }

    /**
     * Returns true if the given snapshot should be stored externally.
     * Only user snapshots (non-ephemeral, non-system) qualify.
     */
    public boolean shouldStoreExternally(String snapshotName, boolean ephemeral, String keyspace)
    {
        if (!isEnabled())
            return false;

        // Ephemeral snapshots stay local (they are cleared on restart)
        if (ephemeral)
            return false;

        // System keyspace snapshots stay local
        if (org.apache.cassandra.schema.SchemaConstants.isLocalSystemKeyspace(keyspace)
            || org.apache.cassandra.schema.SchemaConstants.isReplicatedSystemKeyspace(keyspace))
            return false;

        // Diagnostic/repair snapshots have known prefixes — keep them local
        if (snapshotName.startsWith("pre-") || snapshotName.startsWith("repair-")
            || snapshotName.startsWith("truncated-") || snapshotName.startsWith("dropped-"))
            return false;

        return true;
    }

    // ========================= Path Resolution =========================

    /**
     * Returns the node-level base directory:
     * {@code <snapshot_root_dir>/<cluster>/<dc>/<host_id>}
     */
    public File getNodeBaseDir()
    {
        String rootDir = DatabaseDescriptor.getSnapshotDirectory();
        String cluster = sanitizePath(DatabaseDescriptor.getClusterName());
        String dc = sanitizePath(getDatacenter());
        String hostId = getHostId();

        return new File(new File(new File(new File(rootDir), cluster), dc), hostId);
    }

    /**
     * Returns the data directory for a specific table:
     * {@code <node_base>/data/<keyspace>/<table_name>-<table_id>}
     */
    public File getTableDataDir(String keyspace, String tableName, String tableId)
    {
        File nodeBase = getNodeBaseDir();
        String tableDir = tableName + "-" + tableId;
        return new File(new File(new File(nodeBase, DATA_SUBDIR), keyspace), tableDir);
    }

    /**
     * Returns the flat SSTable pool directory for a table:
     * {@code <table_data_dir>/sstables/}
     */
    public File getSSTablePoolDir(String keyspace, String tableName, String tableId)
    {
        return new File(getTableDataDir(keyspace, tableName, tableId), SSTABLES_SUBDIR);
    }

    /**
     * Returns the manifests directory for a table:
     * {@code <table_data_dir>/manifests/}
     */
    public File getManifestsDir(String keyspace, String tableName, String tableId)
    {
        return new File(getTableDataDir(keyspace, tableName, tableId), MANIFESTS_SUBDIR);
    }

    /**
     * Returns the manifest file for a specific snapshot tag:
     * {@code <table_data_dir>/manifests/<tag>.json}
     */
    public File getManifestFile(String keyspace, String tableName, String tableId, String snapshotTag)
    {
        return new File(getManifestsDir(keyspace, tableName, tableId), snapshotTag + MANIFEST_EXT);
    }

    /**
     * Returns the backups data directory for a specific table:
     * {@code <node_base>/backups/<keyspace>/<table_name>-<table_id>/sstables/}
     */
    public File getBackupSSTablePoolDir(String keyspace, String tableName, String tableId)
    {
        File nodeBase = getNodeBaseDir();
        String tableDir = tableName + "-" + tableId;
        return new File(new File(new File(new File(nodeBase, BACKUPS_SUBDIR), keyspace), tableDir), SSTABLES_SUBDIR);
    }

    /**
     * Returns the backup manifests directory for a specific table:
     * {@code <node_base>/backups/<keyspace>/<table_name>-<table_id>/manifests/}
     */
    public File getBackupManifestsDir(String keyspace, String tableName, String tableId)
    {
        File nodeBase = getNodeBaseDir();
        String tableDir = tableName + "-" + tableId;
        return new File(new File(new File(new File(nodeBase, BACKUPS_SUBDIR), keyspace), tableDir), MANIFESTS_SUBDIR);
    }

    // ========================= Snapshot Operations =========================

    /**
     * Copies SSTables to the external snapshot storage with deduplication.
     *
     * For each SSTable, checks if it already exists in the flat pool (by UUID identifier).
     * Only copies if the SSTable is not already present. Writes an enhanced manifest
     * containing token info, schema, and SSTable ID references.
     *
     * @return the set of SSTable IDs that were copied (for the manifest)
     */
    public Set<String> copySSTablesForSnapshot(Collection<SSTableReader> sstables,
                                               String keyspace,
                                               String tableName,
                                               String tableId,
                                               RateLimiter rateLimiter)
    {
        File sstablePoolDir = getSSTablePoolDir(keyspace, tableName, tableId);
        if (!sstablePoolDir.exists())
            sstablePoolDir.tryCreateDirectories();

        Set<String> sstableIds = new LinkedHashSet<>();
        long bytesPerSecond = DatabaseDescriptor.getSnapshotCopyBytesPerSecond();

        for (SSTableReader ssTable : sstables)
        {
            SSTableId id = ssTable.descriptor.id;
            String idStr = id.toString();
            sstableIds.add(idStr);

            // Copy each component, deduplicating by checking existence
            try
            {
                Descriptor descriptor = ssTable.descriptor;
                for (Component component : ssTable.getComponents())
                {
                    File sourceFile = new File(descriptor.filenameFor(component));
                    if (!sourceFile.exists())
                        continue;

                    // Use original SSTable filename to preserve version-id-format-component naming
                    // that Cassandra tools (sstableloader, etc.) expect for parsing
                    String deduplicatedName = sourceFile.name();
                    File targetFile = new File(sstablePoolDir, deduplicatedName);

                    if (targetFile.exists())
                    {
                        logger.trace("SSTable component already in pool, skipping: {}", targetFile);
                        continue;
                    }

                    // Rate-limit by bytes if configured
                    if (bytesPerSecond > 0)
                    {
                        long fileSize = sourceFile.length();
                        if (fileSize > 0)
                        {
                            // Acquire permits proportional to file size (1 permit = 1 byte)
                            // Split into chunks to avoid blocking too long on large files
                            long remaining = fileSize;
                            while (remaining > 0)
                            {
                                int chunk = (int) Math.min(remaining, 1024 * 1024); // 1MB chunks
                                rateLimiter.acquire(chunk);
                                remaining -= chunk;
                            }
                        }
                    }
                    else if (rateLimiter != null)
                    {
                        rateLimiter.acquire();
                    }

                    Files.copy(sourceFile.toPath(), targetFile.toPath(), StandardCopyOption.COPY_ATTRIBUTES);
                    logger.trace("Copied SSTable component {} to pool {}", sourceFile.name(), targetFile);
                }
            }
            catch (IOException e)
            {
                throw new FSWriteError(e, sstablePoolDir);
            }
        }

        return sstableIds;
    }

    /**
     * Writes an enhanced manifest for an external snapshot.
     */
    public void writeManifest(String snapshotTag,
                              String keyspace,
                              String tableName,
                              String tableId,
                              List<String> files,
                              Set<String> sstableIds,
                              DurationSpec.IntSecondsBound ttl,
                              Instant creationTime,
                              String schemaCql,
                              String schemaVersion)
    {
        File manifestFile = getManifestFile(keyspace, tableName, tableId, snapshotTag);
        if (!manifestFile.parent().exists())
            manifestFile.parent().tryCreateDirectories();

        List<String> tokens = getTokenStrings();
        String hostId = getHostId();

        ExternalSnapshotManifest manifest = new ExternalSnapshotManifest(
            files, sstableIds, ttl, creationTime, tokens, schemaVersion, schemaCql, keyspace, tableName, hostId
        );

        try
        {
            manifest.serializeToJsonFile(manifestFile);
            logger.debug("Wrote external snapshot manifest for {}.{} tag={} at {}", keyspace, tableName, snapshotTag, manifestFile);
        }
        catch (IOException e)
        {
            throw new FSWriteError(e, manifestFile);
        }
    }

    // ========================= Cleanup with Reference Counting =========================

    /**
     * Clears an external snapshot with reference-counted SSTable deletion.
     *
     * 1. Reads the manifest for the target snapshot tag
     * 2. Deletes the manifest file
     * 3. For each SSTable ID in the deleted manifest, checks all remaining manifests
     * 4. If no other manifest references the SSTable, deletes its files from the pool
     */
    public void clearSnapshot(String snapshotTag, String keyspace, String tableName, String tableId)
    {
        File manifestFile = getManifestFile(keyspace, tableName, tableId, snapshotTag);
        if (!manifestFile.exists())
        {
            logger.debug("No external manifest found for {}.{} tag={}", keyspace, tableName, snapshotTag);
            return;
        }

        ExternalSnapshotManifest manifest;
        try
        {
            manifest = ExternalSnapshotManifest.deserializeFromJsonFile(manifestFile);
        }
        catch (IOException e)
        {
            logger.warn("Cannot read manifest for snapshot {} of {}.{}, removing manifest anyway", snapshotTag, keyspace, tableName, e);
            manifestFile.tryDelete();
            return;
        }

        // Delete the manifest first
        manifestFile.tryDelete();
        logger.debug("Removed manifest for snapshot {} of {}.{}", snapshotTag, keyspace, tableName);

        if (manifest.getSstableIds() == null || manifest.getSstableIds().isEmpty())
            return;

        // Collect SSTable IDs still referenced by remaining manifests
        Set<String> referencedIds = collectReferencedSSTableIds(keyspace, tableName, tableId);

        // Delete SSTable files not referenced by any remaining manifest
        File poolDir = getSSTablePoolDir(keyspace, tableName, tableId);
        for (String sstableId : manifest.getSstableIds())
        {
            if (referencedIds.contains(sstableId))
            {
                logger.trace("SSTable {} still referenced by other snapshots, keeping", sstableId);
                continue;
            }

            deleteSSTableFromPool(poolDir, sstableId);
        }
    }

    /**
     * Clears all external snapshots for a table (used when clearing all snapshots).
     */
    public void clearAllSnapshots(String keyspace, String tableName, String tableId)
    {
        File manifestsDir = getManifestsDir(keyspace, tableName, tableId);
        if (!manifestsDir.exists())
            return;

        File[] manifests = manifestsDir.tryList();
        if (manifests == null)
            return;

        for (File mf : manifests)
        {
            if (mf.name().endsWith(MANIFEST_EXT))
            {
                String tag = mf.name().substring(0, mf.name().length() - MANIFEST_EXT.length());
                clearSnapshot(tag, keyspace, tableName, tableId);
            }
        }
    }

    /**
     * Scans all remaining manifests for a table and returns the set of all referenced SSTable IDs.
     */
    @VisibleForTesting
    Set<String> collectReferencedSSTableIds(String keyspace, String tableName, String tableId)
    {
        File manifestsDir = getManifestsDir(keyspace, tableName, tableId);
        Set<String> referenced = new HashSet<>();

        if (!manifestsDir.exists())
            return referenced;

        File[] manifestFiles = manifestsDir.tryList();
        if (manifestFiles == null)
            return referenced;

        for (File mf : manifestFiles)
        {
            if (!mf.name().endsWith(MANIFEST_EXT))
                continue;

            try
            {
                ExternalSnapshotManifest m = ExternalSnapshotManifest.deserializeFromJsonFile(mf);
                if (m.getSstableIds() != null)
                    referenced.addAll(m.getSstableIds());
            }
            catch (IOException e)
            {
                logger.warn("Could not read manifest {}, skipping for reference counting", mf, e);
            }
        }

        return referenced;
    }

    /**
     * Deletes all component files for an SSTable from the pool directory.
     */
    private void deleteSSTableFromPool(File poolDir, String sstableId)
    {
        if (!poolDir.exists())
            return;

        File[] files = poolDir.tryList();
        if (files == null)
            return;

        for (File f : files)
        {
            // SSTable filenames are <version>-<id>-<format>-<component>, so the id
            // appears in the middle of the name. Match files containing the id.
            if (f.name().contains(sstableId))
            {
                logger.trace("Deleting unreferenced SSTable component: {}", f);
                f.tryDelete();
            }
        }
    }

    // ========================= Incremental Backup Support =========================

    /**
     * Copies an SSTable to the external backup pool for incremental backups.
     * Called when incremental_backups = true and snapshot_root_dir is configured.
     */
    public void copySSTableForIncrementalBackup(SSTableReader ssTable,
                                                String keyspace,
                                                String tableName,
                                                String tableId)
    {
        if (!isEnabled())
            return;

        File backupPoolDir = getBackupSSTablePoolDir(keyspace, tableName, tableId);
        if (!backupPoolDir.exists())
            backupPoolDir.tryCreateDirectories();

        String idStr = ssTable.descriptor.id.toString();

        try
        {
            Descriptor descriptor = ssTable.descriptor;
            for (Component component : ssTable.getComponents())
            {
                File sourceFile = new File(descriptor.filenameFor(component));
                if (!sourceFile.exists())
                    continue;

                String deduplicatedName = sourceFile.name();
                File targetFile = new File(backupPoolDir, deduplicatedName);

                if (targetFile.exists())
                    continue;

                Files.copy(sourceFile.toPath(), targetFile.toPath(), StandardCopyOption.COPY_ATTRIBUTES);
                logger.trace("Copied SSTable component {} to backup pool {}", sourceFile.name(), targetFile);
            }
        }
        catch (IOException e)
        {
            logger.warn("Failed to copy SSTable {} to external backup pool", ssTable.getFilename(), e);
        }
    }

    // ========================= Listing =========================

    /**
     * Lists all external snapshots across all keyspaces/tables for this node.
     * When running in a tool context (e.g., nodetool), falls back to scanning
     * the entire snapshot root directory since StorageService is not available.
     *
     * @return Map of snapshot tag -> list of manifests (one per table)
     */
    public Map<String, List<ExternalSnapshotManifest>> listAllExternalSnapshots()
    {
        Map<String, List<ExternalSnapshotManifest>> result = new LinkedHashMap<>();

        // In tool context (nodetool), StorageService isn't available, so scan the entire root
        File nodeBase;
        try
        {
            nodeBase = getNodeBaseDir();
        }
        catch (Exception e)
        {
            // Fall back to scanning the entire snapshot root
            return listAllExternalSnapshotsFromRoot();
        }

        // If host_id resolved to "unknown", scan from root instead
        if (nodeBase.path().contains("/unknown"))
            return listAllExternalSnapshotsFromRoot();

        File dataDir = new File(nodeBase, DATA_SUBDIR);
        if (!dataDir.exists())
            return result;

        // Walk: data/<ks>/<table>/manifests/<tag>.json
        File[] keyspaceDirs = dataDir.tryList();
        if (keyspaceDirs == null)
            return result;

        for (File ksDir : keyspaceDirs)
        {
            if (!ksDir.isDirectory())
                continue;

            File[] tableDirs = ksDir.tryList();
            if (tableDirs == null)
                continue;

            for (File tableDir : tableDirs)
            {
                if (!tableDir.isDirectory())
                    continue;

                File manifestsDir = new File(tableDir, MANIFESTS_SUBDIR);
                if (!manifestsDir.exists())
                    continue;

                File[] manifests = manifestsDir.tryList();
                if (manifests == null)
                    continue;

                for (File mf : manifests)
                {
                    if (!mf.name().endsWith(MANIFEST_EXT))
                        continue;

                    String tag = mf.name().substring(0, mf.name().length() - MANIFEST_EXT.length());
                    try
                    {
                        ExternalSnapshotManifest manifest = ExternalSnapshotManifest.deserializeFromJsonFile(mf);
                        result.computeIfAbsent(tag, k -> new ArrayList<>()).add(manifest);
                    }
                    catch (IOException e)
                    {
                        logger.warn("Could not read external manifest {}", mf, e);
                    }
                }
            }
        }

        return result;
    }

    /**
     * Scans the entire snapshot root directory for manifests, used when
     * running in a tool context (e.g., nodetool) where StorageService is unavailable.
     * Walks: root/&lt;cluster&gt;/&lt;dc&gt;/&lt;host_id&gt;/data/&lt;ks&gt;/&lt;table&gt;/manifests/&lt;tag&gt;.json
     */
    private Map<String, List<ExternalSnapshotManifest>> listAllExternalSnapshotsFromRoot()
    {
        Map<String, List<ExternalSnapshotManifest>> result = new LinkedHashMap<>();
        String rootDir = DatabaseDescriptor.getSnapshotDirectory();
        if (rootDir == null)
            return result;

        File root = new File(rootDir);
        if (!root.exists())
            return result;

        // Walk: root/<cluster>/<dc>/<host_id>/data/<ks>/<table>/manifests/<tag>.json
        File[] clusterDirs = root.tryList();
        if (clusterDirs == null) return result;

        for (File clusterDir : clusterDirs)
        {
            if (!clusterDir.isDirectory()) continue;
            File[] dcDirs = clusterDir.tryList();
            if (dcDirs == null) continue;

            for (File dcDir : dcDirs)
            {
                if (!dcDir.isDirectory()) continue;
                File[] hostDirs = dcDir.tryList();
                if (hostDirs == null) continue;

                for (File hostDir : hostDirs)
                {
                    if (!hostDir.isDirectory()) continue;
                    File dataDir = new File(hostDir, DATA_SUBDIR);
                    if (!dataDir.exists()) continue;

                    scanDataDirForManifests(dataDir, result);
                }
            }
        }

        return result;
    }

    /**
     * Scans a data directory for manifests, populating the result map.
     */
    private void scanDataDirForManifests(File dataDir, Map<String, List<ExternalSnapshotManifest>> result)
    {
        File[] keyspaceDirs = dataDir.tryList();
        if (keyspaceDirs == null) return;

        for (File ksDir : keyspaceDirs)
        {
            if (!ksDir.isDirectory()) continue;
            File[] tableDirs = ksDir.tryList();
            if (tableDirs == null) continue;

            for (File tableDir : tableDirs)
            {
                if (!tableDir.isDirectory()) continue;
                File manifestsDir = new File(tableDir, MANIFESTS_SUBDIR);
                if (!manifestsDir.exists()) continue;

                File[] manifests = manifestsDir.tryList();
                if (manifests == null) continue;

                for (File mf : manifests)
                {
                    if (!mf.name().endsWith(MANIFEST_EXT)) continue;
                    String tag = mf.name().substring(0, mf.name().length() - MANIFEST_EXT.length());
                    try
                    {
                        ExternalSnapshotManifest manifest = ExternalSnapshotManifest.deserializeFromJsonFile(mf);
                        result.computeIfAbsent(tag, k -> new ArrayList<>()).add(manifest);
                    }
                    catch (IOException e)
                    {
                        logger.warn("Could not read external manifest {}", mf, e);
                    }
                }
            }
        }
    }

    /**
     * Lists all incremental backup SSTables for a table.
     *
     * @return list of SSTable file names in the backup pool
     */
    public List<String> listIncrementalBackups(String keyspace, String tableName, String tableId)
    {
        File backupPoolDir = getBackupSSTablePoolDir(keyspace, tableName, tableId);
        if (!backupPoolDir.exists())
            return Collections.emptyList();

        File[] files = backupPoolDir.tryList();
        if (files == null)
            return Collections.emptyList();

        return Arrays.stream(files)
                     .filter(f -> !f.isDirectory())
                     .map(File::name)
                     .collect(Collectors.toList());
    }

    /**
     * Lists all incremental backup SSTables across all keyspaces/tables for this node.
     *
     * @return Map of keyspace -> Map of table -> list of file names
     */
    public Map<String, Map<String, List<String>>> listIncrementalBackups()
    {
        Map<String, Map<String, List<String>>> result = new LinkedHashMap<>();

        File nodeBase = getNodeBaseDir();
        File backupsDir = new File(nodeBase, BACKUPS_SUBDIR);
        if (!backupsDir.exists())
            return result;

        File[] keyspaceDirs = backupsDir.tryList();
        if (keyspaceDirs == null)
            return result;

        for (File ksDir : keyspaceDirs)
        {
            if (!ksDir.isDirectory())
                continue;

            File[] tableDirs = ksDir.tryList();
            if (tableDirs == null)
                continue;

            for (File tableDir : tableDirs)
            {
                if (!tableDir.isDirectory())
                    continue;

                File sstablesDir = new File(tableDir, SSTABLES_SUBDIR);
                if (!sstablesDir.exists())
                    continue;

                File[] files = sstablesDir.tryList();
                if (files == null || files.length == 0)
                    continue;

                List<String> fileNames = Arrays.stream(files)
                                               .filter(f -> !f.isDirectory())
                                               .map(File::name)
                                               .collect(Collectors.toList());

                if (!fileNames.isEmpty())
                {
                    result.computeIfAbsent(ksDir.name(), k -> new LinkedHashMap<>())
                          .put(tableDir.name(), fileNames);
                }
            }
        }

        return result;
    }

    /**
     * Clears incremental backup SSTables older than the given timestamp.
     */
    public int clearIncrementalBackups(String keyspace, String tableName, String tableId, Instant olderThan)
    {
        File backupPoolDir = getBackupSSTablePoolDir(keyspace, tableName, tableId);
        if (!backupPoolDir.exists())
            return 0;

        File[] files = backupPoolDir.tryList();
        if (files == null)
            return 0;

        int deleted = 0;
        for (File f : files)
        {
            if (f.isDirectory())
                continue;

            if (olderThan != null)
            {
                Instant lastModified = Instant.ofEpochMilli(f.lastModified());
                if (lastModified.isAfter(olderThan))
                    continue;
            }

            if (f.tryDelete())
                deleted++;
        }

        return deleted;
    }

    /**
     * Clears incremental backup SSTables across all (or filtered) keyspaces/tables.
     *
     * @param keyspace optional keyspace filter (null = all)
     * @param table    optional table filter (null = all, requires keyspace)
     * @return number of files deleted
     */
    public long clearIncrementalBackups(String keyspace, String table)
    {
        File nodeBase = getNodeBaseDir();
        File backupsDir = new File(nodeBase, BACKUPS_SUBDIR);
        if (!backupsDir.exists())
            return 0;

        long totalDeleted = 0;

        File[] keyspaceDirs = backupsDir.tryList();
        if (keyspaceDirs == null)
            return 0;

        for (File ksDir : keyspaceDirs)
        {
            if (!ksDir.isDirectory())
                continue;
            if (keyspace != null && !keyspace.equals(ksDir.name()))
                continue;

            File[] tableDirs = ksDir.tryList();
            if (tableDirs == null)
                continue;

            for (File tableDir : tableDirs)
            {
                if (!tableDir.isDirectory())
                    continue;
                if (table != null && !tableDir.name().startsWith(table + "-"))
                    continue;

                File sstablesDir = new File(tableDir, SSTABLES_SUBDIR);
                if (!sstablesDir.exists())
                    continue;

                File[] files = sstablesDir.tryList();
                if (files == null)
                    continue;

                for (File f : files)
                {
                    if (!f.isDirectory() && f.tryDelete())
                        totalDeleted++;
                }
            }
        }

        return totalDeleted;
    }

    // ========================= External Snapshot Size =========================

    /**
     * Computes the total size of all SSTables in the external snapshot pool for a table.
     */
    public long computeExternalSnapshotSize(String keyspace, String tableName, String tableId)
    {
        File poolDir = getSSTablePoolDir(keyspace, tableName, tableId);
        if (!poolDir.exists())
            return 0L;

        return FileUtils.folderSize(poolDir);
    }

    // ========================= Helpers =========================

    private List<String> getTokenStrings()
    {
        try
        {
            return StorageService.instance.getLocalTokens()
                                         .stream()
                                         .map(Object::toString)
                                         .collect(Collectors.toList());
        }
        catch (Exception e)
        {
            logger.debug("Could not retrieve tokens for manifest", e);
            return Collections.emptyList();
        }
    }

    private String getHostId()
    {
        try
        {
            String hostId = StorageService.instance.getLocalHostId();
            return hostId != null ? hostId : "unknown";
        }
        catch (Exception e)
        {
            return "unknown";
        }
    }

    private String getDatacenter()
    {
        try
        {
            IEndpointSnitch snitch = DatabaseDescriptor.getEndpointSnitch();
            return snitch != null ? snitch.getLocalDatacenter() : "unknown_dc";
        }
        catch (Exception e)
        {
            return "unknown_dc";
        }
    }

    /**
     * Sanitizes a path component by replacing characters not safe for directory names.
     */
    @VisibleForTesting
    static String sanitizePath(String component)
    {
        if (component == null || component.isEmpty())
            return "default";

        return component.replaceAll("[^a-zA-Z0-9._-]", "_");
    }
}
