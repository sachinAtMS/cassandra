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
package org.apache.cassandra.tools.nodetool;

import java.io.PrintStream;
import java.util.List;
import java.util.Map;

import io.airlift.airline.Command;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.service.snapshot.ExternalSnapshotManager;
import org.apache.cassandra.service.snapshot.ExternalSnapshotManifest;
import org.apache.cassandra.tools.NodeProbe;
import org.apache.cassandra.tools.NodeTool.NodeToolCmd;
import org.apache.cassandra.tools.nodetool.formatter.TableBuilder;

@Command(name = "listexternalsnapshots", description = "Lists all external snapshots stored in the snapshot_directory with deduplication details")
public class ListExternalSnapshots extends NodeToolCmd
{
    @Override
    public void execute(NodeProbe probe)
    {
        PrintStream out = probe.output().out;

        // Ensure config is loaded (nodetool runs in a separate JVM)
        DatabaseDescriptor.toolInitialization(false);

        if (!ExternalSnapshotManager.isEnabled())
        {
            out.println("External snapshot storage is not enabled.");
            out.println("Requires: snapshot_directory set and uuid_sstable_identifiers_enabled=true");
            return;
        }

        ExternalSnapshotManager manager = ExternalSnapshotManager.instance();
        Map<String, List<ExternalSnapshotManifest>> snapshots = manager.listAllExternalSnapshots();

        if (snapshots.isEmpty())
        {
            out.println("No external snapshots found.");
            return;
        }

        out.println("External Snapshot Details:");
        out.println("Directory: " + org.apache.cassandra.config.DatabaseDescriptor.getSnapshotDirectory());
        out.println();

        TableBuilder table = new TableBuilder();
        table.add("Snapshot Tag", "Keyspace", "Table", "SSTable IDs", "Files", "Created At", "Expires At", "Host ID");

        for (Map.Entry<String, List<ExternalSnapshotManifest>> entry : snapshots.entrySet())
        {
            String tag = entry.getKey();
            for (ExternalSnapshotManifest manifest : entry.getValue())
            {
                String sstableCount = manifest.getSstableIds() != null
                                      ? String.valueOf(manifest.getSstableIds().size())
                                      : "0";
                String fileCount = manifest.getFiles() != null
                                   ? String.valueOf(manifest.getFiles().size())
                                   : "0";
                String created = manifest.getCreatedAt() != null
                                 ? manifest.getCreatedAt().toString()
                                 : "unknown";
                String expires = manifest.getExpiresAt() != null
                                 ? manifest.getExpiresAt().toString()
                                 : "never";
                String ks = manifest.getKeyspace() != null ? manifest.getKeyspace() : "?";
                String tbl = manifest.getTable() != null ? manifest.getTable() : "?";
                String host = manifest.getHostId() != null ? manifest.getHostId() : "?";

                table.add(tag, ks, tbl, sstableCount, fileCount, created, expires, host);
            }
        }

        table.printTo(out);
        out.println();
    }
}
