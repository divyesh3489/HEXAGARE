import { Card, CardContent } from "@/components/ui/card";

export function Tile({
  label,
  value,
  emphasize,
}: {
  label: string;
  value: string;
  emphasize?: boolean;
}) {
  return (
    <Card>
      <CardContent className="py-4">
        <p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className={emphasize ? "text-xl font-semibold" : "text-lg font-semibold"}>{value}</p>
      </CardContent>
    </Card>
  );
}
