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
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.Set;

import com.fasterxml.jackson.annotation.JsonAutoDetect;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import org.apache.cassandra.config.DurationSpec;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.utils.FBUtilities;

/**
 * Enhanced snapshot manifest for external snapshot storage (snapshot_root_dir).
 *
 * In addition to the standard file list and TTL fields, this manifest stores:
 * <ul>
 *   <li><b>sstable_ids</b> — UUID-based SSTable identifiers for deduplication across snapshots</li>
 *   <li><b>tokens</b> — The token ranges owned by this node at snapshot time (for restore)</li>
 *   <li><b>schema_version</b> — The schema version UUID at snapshot time</li>
 *   <li><b>schema_cql</b> — The CQL CREATE TABLE statement at snapshot time</li>
 *   <li><b>keyspace</b> — The keyspace name</li>
 *   <li><b>table</b> — The table name</li>
 *   <li><b>host_id</b> — The host UUID of the node that took the snapshot</li>
 * </ul>
 *
 * The sstable_ids field enables deduplication: when multiple snapshots reference the same
 * SSTable (identified by its UUID), the SSTable is stored only once in the flat data pool.
 * On cleanup, an SSTable is physically deleted only when no other manifest references it.
 */
@JsonAutoDetect(fieldVisibility = JsonAutoDetect.Visibility.ANY,
                getterVisibility = JsonAutoDetect.Visibility.NONE,
                setterVisibility = JsonAutoDetect.Visibility.NONE)
@JsonIgnoreProperties(ignoreUnknown = true)
public class ExternalSnapshotManifest
{
    @JsonProperty("files")
    public final List<String> files;

    @JsonProperty("sstable_ids")
    public final Set<String> sstableIds;

    @JsonProperty("created_at")
    public final Instant createdAt;

    @JsonProperty("expires_at")
    public final Instant expiresAt;

    @JsonProperty("tokens")
    public final List<String> tokens;

    @JsonProperty("schema_version")
    public final String schemaVersion;

    @JsonProperty("schema_cql")
    public final String schemaCql;

    @JsonProperty("keyspace")
    public final String keyspace;

    @JsonProperty("table")
    public final String table;

    @JsonProperty("host_id")
    public final String hostId;

    /** Needed for Jackson deserialization */
    @SuppressWarnings("unused")
    private ExternalSnapshotManifest()
    {
        this.files = null;
        this.sstableIds = null;
        this.createdAt = null;
        this.expiresAt = null;
        this.tokens = null;
        this.schemaVersion = null;
        this.schemaCql = null;
        this.keyspace = null;
        this.table = null;
        this.hostId = null;
    }

    public ExternalSnapshotManifest(List<String> files,
                                    Set<String> sstableIds,
                                    DurationSpec.IntSecondsBound ttl,
                                    Instant creationTime,
                                    List<String> tokens,
                                    String schemaVersion,
                                    String schemaCql,
                                    String keyspace,
                                    String table,
                                    String hostId)
    {
        this.files = files;
        this.sstableIds = sstableIds;
        this.createdAt = creationTime;
        this.expiresAt = ttl == null ? null : creationTime.plusSeconds(ttl.toSeconds());
        this.tokens = tokens;
        this.schemaVersion = schemaVersion;
        this.schemaCql = schemaCql;
        this.keyspace = keyspace;
        this.table = table;
        this.hostId = hostId;
    }

    public List<String> getFiles()
    {
        return files;
    }

    public Set<String> getSstableIds()
    {
        return sstableIds;
    }

    public Instant getCreatedAt()
    {
        return createdAt;
    }

    public Instant getExpiresAt()
    {
        return expiresAt;
    }

    public List<String> getTokens()
    {
        return tokens;
    }

    public String getSchemaVersion()
    {
        return schemaVersion;
    }

    public String getSchemaCql()
    {
        return schemaCql;
    }

    public String getKeyspace()
    {
        return keyspace;
    }

    public String getTable()
    {
        return table;
    }

    public String getHostId()
    {
        return hostId;
    }

    public boolean isExpired(Instant now)
    {
        return expiresAt != null && expiresAt.compareTo(now) < 0;
    }

    public void serializeToJsonFile(File outputFile) throws IOException
    {
        FBUtilities.serializeToJsonFile(this, outputFile);
    }

    public static ExternalSnapshotManifest deserializeFromJsonFile(File file) throws IOException
    {
        return FBUtilities.deserializeFromJsonFile(ExternalSnapshotManifest.class, file);
    }

    @Override
    public boolean equals(Object o)
    {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        ExternalSnapshotManifest that = (ExternalSnapshotManifest) o;
        return Objects.equals(files, that.files)
               && Objects.equals(sstableIds, that.sstableIds)
               && Objects.equals(createdAt, that.createdAt)
               && Objects.equals(expiresAt, that.expiresAt)
               && Objects.equals(tokens, that.tokens)
               && Objects.equals(schemaVersion, that.schemaVersion)
               && Objects.equals(keyspace, that.keyspace)
               && Objects.equals(table, that.table)
               && Objects.equals(hostId, that.hostId);
    }

    @Override
    public int hashCode()
    {
        return Objects.hash(files, sstableIds, createdAt, expiresAt, tokens, schemaVersion, keyspace, table, hostId);
    }
}
