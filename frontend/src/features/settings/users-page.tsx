import { useState } from "react";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useHasPermission } from "@/hooks/use-auth";
import { useUserMutations, useUsers } from "./hooks";
import { ROLES, type AdminUser, type Role, type UserCreateBody } from "./types";

const selectClass =
  "h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm " +
  "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

function emptyDraft(): UserCreateBody {
  return { email: "", password: "", first_name: "", last_name: "", phone: "", role: "Cashier" };
}

export function UsersPage() {
  const canManage = useHasPermission()("users.manage");
  const [roleFilter, setRoleFilter] = useState("");
  const { data, isPending, error } = useUsers({ role: roleFilter || undefined, page_size: 200 });
  const { create, update, deactivate, reactivate } = useUserMutations();

  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<UserCreateBody>(emptyDraft());
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editRole, setEditRole] = useState<Role>("Cashier");

  const users = data?.data ?? [];

  const startNew = () => {
    setDraft(emptyDraft());
    setCreating(true);
    setFormError(null);
    setFieldErrors({});
  };

  const submitNew = async () => {
    setFormError(null);
    setFieldErrors({});
    try {
      await create.mutateAsync(draft);
      setCreating(false);
    } catch (err) {
      if (err instanceof ApiError && err.fields) {
        setFieldErrors(err.fields);
        setFormError(err.message);
      } else {
        setFormError(err instanceof Error ? err.message : "Could not create the user.");
      }
    }
  };

  const startEditRole = (user: AdminUser) => {
    setEditingId(user.id);
    setEditRole(user.role ?? "Cashier");
  };

  const submitRole = async (id: number) => {
    await update.mutateAsync({ id, body: { role: editRole } });
    setEditingId(null);
  };

  return (
    <div>
      <PageHeader
        title="Users"
        description="Create accounts and assign roles. Roles and their permissions are fixed -- see Roles & Permissions."
        actions={
          canManage && !creating ? <Button onClick={startNew}>New user</Button> : undefined
        }
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <select
          className={selectClass}
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
        >
          <option value="">All roles</option>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </div>

      {creating && (
        <Card className="mb-4">
          <CardContent className="space-y-4 py-5">
            <h3 className="font-medium">New user</h3>
            {formError && <p className="text-sm text-destructive">{formError}</p>}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label>Email</Label>
                <Input
                  type="email"
                  value={draft.email}
                  onChange={(e) => setDraft((d) => ({ ...d, email: e.target.value }))}
                />
                {fieldErrors.email && (
                  <p className="text-xs text-destructive">{fieldErrors.email.join(" ")}</p>
                )}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Password</Label>
                <Input
                  type="password"
                  value={draft.password}
                  onChange={(e) => setDraft((d) => ({ ...d, password: e.target.value }))}
                />
                {fieldErrors.password && (
                  <p className="text-xs text-destructive">{fieldErrors.password.join(" ")}</p>
                )}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>First name</Label>
                <Input
                  value={draft.first_name}
                  onChange={(e) => setDraft((d) => ({ ...d, first_name: e.target.value }))}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Last name</Label>
                <Input
                  value={draft.last_name}
                  onChange={(e) => setDraft((d) => ({ ...d, last_name: e.target.value }))}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Phone</Label>
                <Input
                  value={draft.phone}
                  onChange={(e) => setDraft((d) => ({ ...d, phone: e.target.value }))}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Role</Label>
                <select
                  className={selectClass}
                  value={draft.role}
                  onChange={(e) => setDraft((d) => ({ ...d, role: e.target.value as Role }))}
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="flex gap-2">
              <Button onClick={submitNew} disabled={create.isPending}>
                Create
              </Button>
              <Button variant="outline" onClick={() => setCreating(false)}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {error && <p className="text-sm text-destructive">Couldn’t load users.</p>}

      {!error && (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-3 font-medium">Email</th>
                    <th className="px-4 py-3 font-medium">Name</th>
                    <th className="px-4 py-3 font-medium">Role</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Last login</th>
                    {canManage && <th className="px-4 py-3" />}
                  </tr>
                </thead>
                <tbody>
                  {isPending && (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                        Loading…
                      </td>
                    </tr>
                  )}
                  {!isPending && users.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">
                        No users yet.
                      </td>
                    </tr>
                  )}
                  {users.map((user) => (
                    <tr key={user.id} className="border-b last:border-0">
                      <td className="px-4 py-3">{user.email}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {[user.first_name, user.last_name].filter(Boolean).join(" ") || "—"}
                      </td>
                      <td className="px-4 py-3">
                        {editingId === user.id ? (
                          <select
                            className={selectClass}
                            value={editRole}
                            onChange={(e) => setEditRole(e.target.value as Role)}
                          >
                            {ROLES.map((r) => (
                              <option key={r} value={r}>
                                {r}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <Badge variant="secondary">{user.role ?? "—"}</Badge>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={user.is_active ? "default" : "destructive"}>
                          {user.is_active ? "Active" : "Inactive"}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                        {user.last_login ? new Date(user.last_login).toLocaleString() : "Never"}
                      </td>
                      {canManage && (
                        <td className="px-4 py-3 text-right whitespace-nowrap">
                          {editingId === user.id ? (
                            <div className="flex justify-end gap-2">
                              <Button
                                size="sm"
                                onClick={() => submitRole(user.id)}
                                disabled={update.isPending}
                              >
                                Save
                              </Button>
                              <Button size="sm" variant="outline" onClick={() => setEditingId(null)}>
                                Cancel
                              </Button>
                            </div>
                          ) : (
                            <div className="flex justify-end gap-2">
                              <Button size="sm" variant="ghost" onClick={() => startEditRole(user)}>
                                Change role
                              </Button>
                              {user.is_active ? (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => deactivate.mutate(user.id)}
                                  disabled={deactivate.isPending}
                                >
                                  Deactivate
                                </Button>
                              ) : (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => reactivate.mutate(user.id)}
                                  disabled={reactivate.isPending}
                                >
                                  Reactivate
                                </Button>
                              )}
                            </div>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
