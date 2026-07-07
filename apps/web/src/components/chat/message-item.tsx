interface MessageItemProps {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
}

export function MessageItem({ role, content }: MessageItemProps) {
  const isUser = role === "user";

  return (
    <article
      className={`flex w-full gap-3 ${isUser ? "justify-end" : "justify-start"}`}
    >
      {!isUser ? (
        <div className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full bg-[#242424] text-[11px] font-medium text-white">
          A
        </div>
      ) : null}
      <div
        className={`max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-6 shadow-sm ${
          isUser
            ? "rounded-tr-md bg-[#242424] text-white"
            : "rounded-tl-md border bg-white"
        }`}
      >
        <div
          className={`mb-1 text-[11px] font-medium uppercase ${
            isUser ? "text-white/60" : "text-muted-foreground"
          }`}
        >
          {role}
        </div>
        <p>{content}</p>
      </div>
      {isUser ? (
        <div className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full border bg-white text-[11px] font-medium">
          U
        </div>
      ) : null}
    </article>
  );
}

