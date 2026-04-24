import { PageHeader } from "../components/common/PageHeader";
import { InfoCard } from "../components/common/InfoCard";
import { ApiHint } from "../components/common/ApiHint";

type PlaceholderPageProps = {
  icon: string;
  title: string;
  subtitle: string;
  endpointSuggestion: string;
};

export function PlaceholderPage({
  icon,
  title,
  subtitle,
  endpointSuggestion
}: PlaceholderPageProps) {
  return (
    <div>
      <PageHeader icon={icon} title={title} subtitle={subtitle} />
      <InfoCard
        title="Ready for API integration"
        hint="Frontend module is already separated and can directly consume your Railway backend."
      >
        <p className="text-body">Suggested endpoint: <code>{endpointSuggestion}</code></p>
        <ApiHint />
      </InfoCard>
    </div>
  );
}
