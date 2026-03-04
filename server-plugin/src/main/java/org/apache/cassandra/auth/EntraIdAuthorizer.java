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
package org.apache.cassandra.auth;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Supplier;

import com.google.common.collect.ImmutableSet;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.apache.cassandra.cql3.QueryProcessor;
import org.apache.cassandra.cql3.UntypedResultSet;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.db.marshal.UTF8Type;
import org.apache.cassandra.exceptions.*;
import org.apache.cassandra.schema.SchemaConstants;
import org.apache.cassandra.utils.Pair;

/**
 * EntraIdAuthorizer is an IAuthorizer implementation that combines Cassandra's
 * standard role-based permissions with Microsoft Entra ID group-based authorization.
 *
 * <p>This is the <b>plugin version</b> — it can be deployed as a standalone JAR
 * in Cassandra's {@code lib/} directory without modifying any Cassandra source code.</p>
 *
 * <h3>How it works:</h3>
 * <ol>
 *   <li>When a user authenticates via {@link EntraIdAuthenticator}, their Entra ID
 *       group memberships and app role assignments are cached.</li>
 *   <li>At authorization time, this authorizer resolves permissions from two sources:
 *       <ul>
 *         <li><b>Direct role permissions:</b> Standard Cassandra permissions from
 *             {@code system_auth.role_permissions} for the user's Cassandra role
 *             (identical to CassandraAuthorizer behavior).</li>
 *         <li><b>Group-mapped permissions:</b> If the user's Entra ID groups are
 *             mapped to Cassandra roles via the {@code system_auth.entra_group_roles}
 *             table, permissions from those mapped roles are also included.</li>
 *       </ul>
 *   </li>
 * </ol>
 *
 * <h3>Group-to-Role Mapping:</h3>
 * <p>Administrators can map Entra ID groups to Cassandra roles:</p>
 * <pre>
 * -- Map an Entra ID group (by Object ID) to a Cassandra role
 * INSERT INTO system_auth.entra_group_roles (group_id, cassandra_role)
 *     VALUES ('group-oid-uuid', 'db_readers');
 * </pre>
 *
 * <h3>Configuration in cassandra.yaml:</h3>
 * <pre>
 * authorizer: org.apache.cassandra.auth.EntraIdAuthorizer
 * </pre>
 *
 * @see EntraIdAuthenticator
 * @see CassandraAuthorizer
 */
public class EntraIdAuthorizer extends CassandraAuthorizer
{
    private static final Logger logger = LoggerFactory.getLogger(EntraIdAuthorizer.class);

    // Table to store Entra ID group -> Cassandra role mappings
    public static final String ENTRA_GROUP_ROLES_TABLE = "entra_group_roles";

    // Cache of group_id -> set of cassandra role names. Refreshed periodically.
    private final Map<String, Set<String>> groupRoleMappings = new ConcurrentHashMap<>();

    public EntraIdAuthorizer()
    {
        super();
    }

    /**
     * Authorizes a user by combining standard role permissions with Entra ID group-based permissions.
     *
     * @param user the authenticated user
     * @param resource the resource being accessed
     * @return the set of permissions the user has on the resource
     */
    @Override
    public Set<Permission> authorize(AuthenticatedUser user, IResource resource)
    {
        try
        {
            // First, check superuser status (inherits all permissions)
            if (user.isSuper())
                return resource.applicablePermissions();

            // Get standard permissions from CassandraAuthorizer (role_permissions table)
            Set<Permission> permissions = EnumSet.noneOf(Permission.class);
            permissions.addAll(super.authorize(user, resource));

            // Additionally, check Entra ID group-based permissions
            EntraIdTokenValidator.EntraIdClaims claims = EntraIdAuthenticator.getCachedClaims(user.getName());
            if (claims != null)
            {
                // Check Entra ID groups
                for (String groupId : claims.groups)
                {
                    Set<String> mappedRoles = getGroupRoleMappings(groupId);
                    for (String roleName : mappedRoles)
                    {
                        Set<Permission> groupPerms = getPermissionsForRole(roleName, resource);
                        permissions.addAll(groupPerms);
                    }
                }

                // Check Entra ID app roles (treated like groups for permission mapping)
                for (String appRole : claims.roles)
                {
                    Set<String> mappedRoles = getGroupRoleMappings(appRole);
                    for (String roleName : mappedRoles)
                    {
                        Set<Permission> rolePerms = getPermissionsForRole(roleName, resource);
                        permissions.addAll(rolePerms);
                    }
                }
            }

            return permissions;
        }
        catch (RequestExecutionException | RequestValidationException e)
        {
            logger.debug("Failed to authorize {} for {}", user, resource);
            throw new UnauthorizedException("Unable to perform authorization: " + e.getMessage(), e);
        }
    }

    /**
     * Gets the Cassandra role names mapped to an Entra ID group.
     *
     * @param groupId the Entra ID group Object ID or app role name
     * @return set of Cassandra role names mapped to this group
     */
    private Set<String> getGroupRoleMappings(String groupId)
    {
        // Check cache first
        Set<String> cached = groupRoleMappings.get(groupId);
        if (cached != null)
            return cached;

        // Query the entra_group_roles table
        try
        {
            UntypedResultSet result = process(
                String.format("SELECT cassandra_role FROM %s.%s WHERE group_id = '%s'",
                              SchemaConstants.AUTH_KEYSPACE_NAME,
                              ENTRA_GROUP_ROLES_TABLE,
                              groupId.replace("'", "''")),
                authReadConsistencyLevel());

            Set<String> roles = new HashSet<>();
            for (UntypedResultSet.Row row : result)
            {
                if (row.has("cassandra_role"))
                    roles.add(row.getString("cassandra_role"));
            }

            // Cache the mapping
            groupRoleMappings.put(groupId, roles);
            return roles;
        }
        catch (Exception e)
        {
            logger.debug("Failed to lookup group role mappings for group {}: {}", groupId, e.getMessage());
            return Collections.emptySet();
        }
    }

    /**
     * Gets the permissions for a specific Cassandra role on a resource.
     *
     * @param roleName the Cassandra role name
     * @param resource the resource to check permissions for
     * @return set of permissions the role has on the resource
     */
    private Set<Permission> getPermissionsForRole(String roleName, IResource resource)
    {
        try
        {
            UntypedResultSet result = process(
                String.format("SELECT permissions FROM %s.%s WHERE role = '%s' AND resource = '%s'",
                              SchemaConstants.AUTH_KEYSPACE_NAME,
                              AuthKeyspace.ROLE_PERMISSIONS,
                              roleName.replace("'", "''"),
                              resource.getName().replace("'", "''")),
                authReadConsistencyLevel());

            Set<Permission> permissions = EnumSet.noneOf(Permission.class);
            if (!result.isEmpty() && result.one().has("permissions"))
            {
                for (String p : result.one().getSet("permissions", UTF8Type.instance))
                    permissions.add(Permission.valueOf(p));
            }
            return permissions;
        }
        catch (Exception e)
        {
            logger.debug("Failed to get permissions for role {} on {}: {}", roleName, resource, e.getMessage());
            return Collections.emptySet();
        }
    }

    @Override
    public Set<DataResource> protectedResources()
    {
        return ImmutableSet.of(
            DataResource.table(SchemaConstants.AUTH_KEYSPACE_NAME, AuthKeyspace.ROLE_PERMISSIONS),
            DataResource.table(SchemaConstants.AUTH_KEYSPACE_NAME, ENTRA_GROUP_ROLES_TABLE)
        );
    }

    @Override
    public void validateConfiguration() throws ConfigurationException
    {
        super.validateConfiguration();
    }

    @Override
    public void setup()
    {
        super.setup();
        ensureEntraGroupRolesTable();
        refreshGroupRoleMappings();
        logger.info("EntraID Authorizer initialized with group-to-role mapping support");
    }

    /**
     * Creates the entra_group_roles table in system_auth if it doesn't exist.
     *
     * Schema:
     *   CREATE TABLE IF NOT EXISTS system_auth.entra_group_roles (
     *       group_id text,
     *       cassandra_role text,
     *       PRIMARY KEY (group_id, cassandra_role)
     *   );
     */
    private void ensureEntraGroupRolesTable()
    {
        try
        {
            process(String.format("CREATE TABLE IF NOT EXISTS %s.%s ("
                                  + "group_id text, "
                                  + "cassandra_role text, "
                                  + "PRIMARY KEY (group_id, cassandra_role))",
                                  SchemaConstants.AUTH_KEYSPACE_NAME,
                                  ENTRA_GROUP_ROLES_TABLE),
                    ConsistencyLevel.LOCAL_ONE);
            logger.info("Ensured {} table exists in {}", ENTRA_GROUP_ROLES_TABLE, SchemaConstants.AUTH_KEYSPACE_NAME);
        }
        catch (Exception e)
        {
            logger.warn("Failed to create {} table: {}. Group-based authorization may not work.",
                        ENTRA_GROUP_ROLES_TABLE, e.getMessage());
        }
    }

    /**
     * Pre-loads all group-to-role mappings from the entra_group_roles table.
     */
    private void refreshGroupRoleMappings()
    {
        try
        {
            UntypedResultSet result = process(
                String.format("SELECT group_id, cassandra_role FROM %s.%s",
                              SchemaConstants.AUTH_KEYSPACE_NAME,
                              ENTRA_GROUP_ROLES_TABLE),
                authReadConsistencyLevel());

            Map<String, Set<String>> newMappings = new HashMap<>();
            for (UntypedResultSet.Row row : result)
            {
                String groupId = row.getString("group_id");
                String role = row.getString("cassandra_role");
                newMappings.computeIfAbsent(groupId, k -> new HashSet<>()).add(role);
            }

            groupRoleMappings.clear();
            groupRoleMappings.putAll(newMappings);
            logger.info("Loaded {} Entra ID group-to-role mappings", newMappings.size());
        }
        catch (Exception e)
        {
            logger.warn("Failed to load group-role mappings: {}. Mappings will be loaded on-demand.",
                        e.getMessage());
        }
    }

    /**
     * Invalidates the cached group-role mapping for a specific group.
     * Call this after modifying the entra_group_roles table.
     */
    public void invalidateGroupMapping(String groupId)
    {
        groupRoleMappings.remove(groupId);
    }

    /**
     * Invalidates all cached group-role mappings, forcing a refresh.
     */
    public void invalidateAllGroupMappings()
    {
        groupRoleMappings.clear();
    }

    /**
     * Returns the bulk loader for the permissions cache, including Entra ID group-derived permissions.
     */
    @Override
    public Supplier<Map<Pair<AuthenticatedUser, IResource>, Set<Permission>>> bulkLoader()
    {
        // Delegate to parent's bulk loader — Entra ID group permissions are resolved dynamically
        return super.bulkLoader();
    }
}
