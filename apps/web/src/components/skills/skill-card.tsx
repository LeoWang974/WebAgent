import { SkillIcon } from "./skill-icon";

interface SkillCardProps {
  description?: string;
  name: string;
  onClick?: () => void;
}

export function SkillCard({ description, name, onClick }: SkillCardProps) {
  return (
    <button
      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-[#e9e9e2]"
      onClick={onClick}
      type="button"
    >
      <SkillIcon />
      <span className="min-w-0">
        <span className="block truncate text-[13px] leading-5">{name}</span>
        {description ? (
          <span className="block text-[11px] text-muted-foreground">
            {description}
          </span>
        ) : null}
      </span>
    </button>
  );
}
