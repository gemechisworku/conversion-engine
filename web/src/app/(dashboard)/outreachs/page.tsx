import { OutreachsList } from "@/components/outreachs-list";

export default function OutreachsPage() {
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-foreground">Outreachs</h1>
        <p className="text-sm text-muted">All drafted/reviewed outreach records across leads.</p>
      </header>
      <OutreachsList />
    </div>
  );
}

