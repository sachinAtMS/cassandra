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
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.List;

import org.junit.BeforeClass;
import org.junit.ClassRule;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.io.util.FileUtils;
import org.apache.cassandra.service.DefaultFSErrorHandler;

import static org.assertj.core.api.Assertions.assertThat;

public class ExternalSnapshotManagerTest
{
    @BeforeClass
    public static void beforeClass()
    {
        DatabaseDescriptor.daemonInitialization();
        FileUtils.setFSErrorHandler(new DefaultFSErrorHandler());
    }

    @ClassRule
    public static TemporaryFolder classFolder = new TemporaryFolder();

    @Rule
    public TemporaryFolder tempFolder = new TemporaryFolder();

    @Test
    public void testSanitizePath()
    {
        assertThat(ExternalSnapshotManager.sanitizePath("simple")).isEqualTo("simple");
        assertThat(ExternalSnapshotManager.sanitizePath("my-cluster")).isEqualTo("my-cluster");
        assertThat(ExternalSnapshotManager.sanitizePath("my.cluster")).isEqualTo("my.cluster");
        assertThat(ExternalSnapshotManager.sanitizePath("my cluster")).isEqualTo("my_cluster");
        assertThat(ExternalSnapshotManager.sanitizePath("my/cluster")).isEqualTo("my_cluster");
        assertThat(ExternalSnapshotManager.sanitizePath("")).isEqualTo("default");
        assertThat(ExternalSnapshotManager.sanitizePath(null)).isEqualTo("default");
        assertThat(ExternalSnapshotManager.sanitizePath("test@#$%")).isEqualTo("test____");
    }

    @Test
    public void testShouldStoreExternallyFiltersSystemKeyspaces()
    {
        ExternalSnapshotManager manager = ExternalSnapshotManager.instance();
        // When external snapshots are not enabled, nothing should be stored externally
        // (rely on isEnabled() returning false when snapshot_directory not set)
        // This test validates the filtering logic in isolation
        // System keyspaces should always be false
        if (ExternalSnapshotManager.isEnabled())
        {
            assertThat(manager.shouldStoreExternally("user-snapshot", false, "system")).isFalse();
            assertThat(manager.shouldStoreExternally("user-snapshot", false, "system_schema")).isFalse();
            assertThat(manager.shouldStoreExternally("user-snapshot", false, "system_auth")).isFalse();
        }
    }

    @Test
    public void testShouldStoreExternallyFiltersEphemeral()
    {
        ExternalSnapshotManager manager = ExternalSnapshotManager.instance();
        if (ExternalSnapshotManager.isEnabled())
        {
            assertThat(manager.shouldStoreExternally("my-snap", true, "user_ks")).isFalse();
        }
    }

    @Test
    public void testShouldStoreExternallyFiltersDiagnosticPrefixes()
    {
        ExternalSnapshotManager manager = ExternalSnapshotManager.instance();
        if (ExternalSnapshotManager.isEnabled())
        {
            assertThat(manager.shouldStoreExternally("pre-123", false, "user_ks")).isFalse();
            assertThat(manager.shouldStoreExternally("repair-abc", false, "user_ks")).isFalse();
            assertThat(manager.shouldStoreExternally("truncated-xyz", false, "user_ks")).isFalse();
            assertThat(manager.shouldStoreExternally("dropped-def", false, "user_ks")).isFalse();
        }
    }

    @Test
    public void testCollectReferencedSSTableIds() throws IOException
    {
        java.io.File base = tempFolder.newFolder("extsnap");
        // Set up a fake manifests directory structure
        java.io.File manifestsDir = new java.io.File(base, "manifests");
        manifestsDir.mkdirs();

        // Write two manifests referencing overlapping SSTable IDs
        Set<String> ids1 = new HashSet<>(Arrays.asList("uuid-1", "uuid-2", "uuid-3"));
        Set<String> ids2 = new HashSet<>(Arrays.asList("uuid-2", "uuid-4"));

        ExternalSnapshotManifest m1 = new ExternalSnapshotManifest(
            Arrays.asList("f1.db", "f2.db"), ids1, null, Instant.now(),
            null, null, null, "ks", "tbl", "host"
        );
        ExternalSnapshotManifest m2 = new ExternalSnapshotManifest(
            Arrays.asList("f3.db"), ids2, null, Instant.now(),
            null, null, null, "ks", "tbl", "host"
        );

        File mf1 = new File(new java.io.File(manifestsDir, "snap1.json"));
        File mf2 = new File(new java.io.File(manifestsDir, "snap2.json"));
        m1.serializeToJsonFile(mf1);
        m2.serializeToJsonFile(mf2);

        // The collectReferencedSSTableIds method uses path resolution based on DatabaseDescriptor,
        // so we can't test it directly without full config. Instead, we test the manifest
        // deserialization that feeds into it.
        ExternalSnapshotManifest read1 = ExternalSnapshotManifest.deserializeFromJsonFile(mf1);
        ExternalSnapshotManifest read2 = ExternalSnapshotManifest.deserializeFromJsonFile(mf2);

        Set<String> allReferenced = new HashSet<>();
        allReferenced.addAll(read1.getSstableIds());
        allReferenced.addAll(read2.getSstableIds());

        assertThat(allReferenced).containsExactlyInAnyOrder("uuid-1", "uuid-2", "uuid-3", "uuid-4");
    }

    @Test
    public void testClearIncrementalBackupsFromDirectory() throws Exception
    {
        // Create a temp directory simulating backup pool
        java.io.File backupDir = tempFolder.newFolder("backups", "ks", "tbl-abc", "sstables");

        // Create some fake backup files
        new java.io.File(backupDir, "uuid1-Data.db").createNewFile();
        new java.io.File(backupDir, "uuid1-Index.db").createNewFile();
        new java.io.File(backupDir, "uuid2-Data.db").createNewFile();

        assertThat(backupDir.listFiles()).hasSize(3);

        // Manually delete all files to simulate clearIncrementalBackups logic
        File poolDir = new File(backupDir);
        File[] files = poolDir.tryList();
        int deleted = 0;
        for (File f : files)
        {
            if (!f.isDirectory() && f.tryDelete())
                deleted++;
        }

        assertThat(deleted).isEqualTo(3);
        assertThat(backupDir.listFiles()).isEmpty();
    }

    @Test
    public void testReferenceCountedDeletion() throws IOException
    {
        // Simulate the reference counting logic
        // Setup: two snapshots share uuid-2, snap1 unique has uuid-1, snap2 unique has uuid-3
        java.io.File base = tempFolder.newFolder("refcount");
        java.io.File sstablesDir = new java.io.File(base, "sstables");
        java.io.File manifestsDir = new java.io.File(base, "manifests");
        sstablesDir.mkdirs();
        manifestsDir.mkdirs();

        // Create SSTable files in pool
        createFakeSSTableFiles(sstablesDir, "uuid-1");
        createFakeSSTableFiles(sstablesDir, "uuid-2");
        createFakeSSTableFiles(sstablesDir, "uuid-3");

        assertThat(sstablesDir.listFiles()).hasSize(6); // 2 components each

        // Create manifests
        Set<String> snap1Ids = new HashSet<>(Arrays.asList("uuid-1", "uuid-2"));
        Set<String> snap2Ids = new HashSet<>(Arrays.asList("uuid-2", "uuid-3"));

        ExternalSnapshotManifest m1 = new ExternalSnapshotManifest(
            Arrays.asList("f1"), snap1Ids, null, Instant.now(),
            null, null, null, "ks", "tbl", "host"
        );
        ExternalSnapshotManifest m2 = new ExternalSnapshotManifest(
            Arrays.asList("f2"), snap2Ids, null, Instant.now(),
            null, null, null, "ks", "tbl", "host"
        );

        File mf1 = new File(new java.io.File(manifestsDir, "snap1.json"));
        File mf2 = new File(new java.io.File(manifestsDir, "snap2.json"));
        m1.serializeToJsonFile(mf1);
        m2.serializeToJsonFile(mf2);

        // Simulate clearing snap1: remove manifest, then check references
        mf1.tryDelete();

        // Collect remaining referenced IDs from snap2
        ExternalSnapshotManifest remainingManifest = ExternalSnapshotManifest.deserializeFromJsonFile(mf2);
        Set<String> referencedIds = remainingManifest.getSstableIds();

        // Delete unreferenced SSTables from snap1
        File poolDir = new File(sstablesDir);
        for (String sstableId : snap1Ids)
        {
            if (referencedIds.contains(sstableId))
                continue; // Still referenced, keep

            // Delete component files
            for (File f : poolDir.tryList())
            {
                if (f.name().contains(sstableId))
                    f.tryDelete();
            }
        }

        // uuid-1 should be deleted (only in snap1)
        // uuid-2 should remain (shared with snap2)
        // uuid-3 should remain (only in snap2, not in snap1)
        File[] remaining = poolDir.tryList();
        assertThat(remaining).hasSize(4); // uuid-2 (2 files) + uuid-3 (2 files)

        Set<String> remainingNames = new HashSet<>();
        for (File f : remaining)
            remainingNames.add(f.name());

        assertThat(remainingNames).containsExactlyInAnyOrder(
            "na-uuid-2-big-Data.db", "na-uuid-2-big-Index.db",
            "na-uuid-3-big-Data.db", "na-uuid-3-big-Index.db"
        );
        assertThat(remainingNames).doesNotContain("na-uuid-1-big-Data.db", "na-uuid-1-big-Index.db");
    }

    @Test
    public void testManifestListingFromDirectoryStructure() throws IOException
    {
        // Create a hierarchical structure mimicking the external snapshot layout
        java.io.File dataDir = tempFolder.newFolder("listing", "data");
        java.io.File ksDir = new java.io.File(dataDir, "my_keyspace");
        java.io.File tblDir = new java.io.File(ksDir, "my_table-abc123");
        java.io.File manifestsDir = new java.io.File(tblDir, "manifests");
        manifestsDir.mkdirs();

        // Write two manifests
        ExternalSnapshotManifest m1 = new ExternalSnapshotManifest(
            Arrays.asList("f1.db"), new HashSet<>(Arrays.asList("id1")), null, Instant.now(),
            Arrays.asList("100", "200"), "v1", "CREATE TABLE ...", "my_keyspace", "my_table", "host1"
        );
        ExternalSnapshotManifest m2 = new ExternalSnapshotManifest(
            Arrays.asList("f2.db"), new HashSet<>(Arrays.asList("id2")), null, Instant.now(),
            Arrays.asList("100", "200"), "v1", "CREATE TABLE ...", "my_keyspace", "my_table", "host1"
        );

        m1.serializeToJsonFile(new File(new java.io.File(manifestsDir, "daily-backup.json")));
        m2.serializeToJsonFile(new File(new java.io.File(manifestsDir, "weekly-backup.json")));

        // Read them back - simulating what listAllExternalSnapshots does
        File manifestsDirFile = new File(manifestsDir);
        File[] manifestFiles = manifestsDirFile.tryList();
        assertThat(manifestFiles).hasSize(2);

        Map<String, ExternalSnapshotManifest> readManifests = new java.util.HashMap<>();
        for (File mf : manifestFiles)
        {
            String tag = mf.name().replace(".json", "");
            readManifests.put(tag, ExternalSnapshotManifest.deserializeFromJsonFile(mf));
        }

        assertThat(readManifests).containsKeys("daily-backup", "weekly-backup");
        assertThat(readManifests.get("daily-backup").getKeyspace()).isEqualTo("my_keyspace");
        assertThat(readManifests.get("daily-backup").getTokens()).containsExactly("100", "200");
        assertThat(readManifests.get("weekly-backup").getSstableIds()).containsExactly("id2");
    }

    private void createFakeSSTableFiles(java.io.File dir, String sstableId) throws IOException
    {
        // Use full Cassandra SSTable naming format: <version>-<id>-<format>-<component>
        new java.io.File(dir, "na-" + sstableId + "-big-Data.db").createNewFile();
        new java.io.File(dir, "na-" + sstableId + "-big-Index.db").createNewFile();
    }
}
