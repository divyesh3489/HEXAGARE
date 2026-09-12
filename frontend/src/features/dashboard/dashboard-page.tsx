import { PageHeader } from "@/components/page-header";
import { useCurrentUser } from "@/hooks/use-auth";
import { AnalyticsSection } from "./analytics-section";
import { FinanceSection } from "./finance-section";
import { InventorySection } from "./inventory-section";
import { SalesSection } from "./sales-section";

export function DashboardPage() {
  const user = useCurrentUser();

  return (
    <div className="space-y-8">
      <PageHeader title="Dashboard" description={user ? `Signed in as ${user.email}` : undefined} />
      <SalesSection />
      <InventorySection />
      <FinanceSection />
      <AnalyticsSection />
    </div>
  );
}
