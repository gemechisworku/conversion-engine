import { LeadDetail } from "@/components/lead-detail";

type PageProps = { params: Promise<{ leadId: string }> };

export default async function LeadPage({ params }: PageProps) {
  const { leadId } = await params;
  return <LeadDetail leadId={leadId} />;
}
