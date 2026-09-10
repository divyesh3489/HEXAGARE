import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useCurrentUser } from "@/hooks/use-auth";

const WIDGET_GROUPS = ["Sales", "Inventory", "Finance", "Analytics"];

export function DashboardPage() {
  const user = useCurrentUser();

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description={
          user ? `Signed in as ${user.email}` : undefined
        }
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {WIDGET_GROUPS.map((group) => (
          <Card key={group}>
            <CardHeader>
              <CardTitle className="text-sm text-muted-foreground">{group}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              Widgets arrive in Phase 16.
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
