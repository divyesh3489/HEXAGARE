import { Construction } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";

/** Placeholder for a domain area that a later phase builds out. */
export function StubPage({ title, phase }: { title: string; phase: string }) {
  return (
    <div>
      <PageHeader title={title} />
      <Card>
        <CardContent className="flex flex-col items-center gap-2 py-16 text-center text-muted-foreground">
          <Construction className="size-8" />
          <p className="text-sm">
            <span className="font-medium text-foreground">{title}</span> is planned for {phase}.
          </p>
          <p className="text-xs">This route is a placeholder in the Phase 1 app shell.</p>
        </CardContent>
      </Card>
    </div>
  );
}
