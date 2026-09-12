import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { useRoles } from "./hooks";

export function RolesPage() {
  const { data, isPending, error } = useRoles();

  if (error) {
    return (
      <div>
        <PageHeader title="Roles & Permissions" />
        <p className="text-sm text-destructive">Couldn’t load the role/permission matrix.</p>
      </div>
    );
  }

  const roles = data?.roles ?? [];
  const permissions = data?.permissions ?? [];
  const heldBy = (codename: string) =>
    new Set(roles.filter((r) => r.permissions.includes(codename)).map((r) => r.role));

  return (
    <div>
      <PageHeader
        title="Roles & Permissions"
        description="Read-only -- roles and their permissions are fixed in the application code."
      />

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Permission</th>
                  {roles.map((r) => (
                    <th key={r.role} className="px-4 py-3 text-center font-medium">
                      {r.role}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {isPending && (
                  <tr>
                    <td colSpan={roles.length + 1} className="px-4 py-8 text-center text-muted-foreground">
                      Loading…
                    </td>
                  </tr>
                )}
                {!isPending &&
                  permissions.map((perm) => {
                    const held = heldBy(perm.codename);
                    return (
                      <tr key={perm.codename} className="border-b last:border-0">
                        <td className="px-4 py-3">
                          <div>{perm.name}</div>
                          <div className="font-mono text-xs text-muted-foreground">
                            {perm.codename}
                          </div>
                        </td>
                        {roles.map((r) => (
                          <td key={r.role} className="px-4 py-3 text-center">
                            {held.has(r.role) ? (
                              <span className="text-primary" aria-label="granted">
                                ✓
                              </span>
                            ) : (
                              <span className="text-muted-foreground/40" aria-label="not granted">
                                —
                              </span>
                            )}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
