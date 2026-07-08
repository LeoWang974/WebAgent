"use client";

import { FormEvent, useEffect, useState } from "react";
import { Loader2, Save } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useUserStore } from "@/stores";

export function ProfileSettings() {
  const { t } = useI18n();
  const user = useUserStore((state) => state.user);
  const saving = useUserStore((state) => state.saving);
  const savedAt = useUserStore((state) => state.savedAt);
  const updateProfile = useUserStore((state) => state.updateProfile);
  const [avatarUrl, setAvatarUrl] = useState("");
  const [email, setEmail] = useState("");
  const [nickname, setNickname] = useState("");

  useEffect(() => {
    setAvatarUrl(user?.avatarUrl ?? "");
    setEmail(user?.email ?? "");
    setNickname(user?.nickname ?? "");
  }, [user]);

  const dirty =
    nickname !== (user?.nickname ?? "") ||
    email !== (user?.email ?? "") ||
    avatarUrl !== (user?.avatarUrl ?? "");
  const valid = nickname.trim().length > 0 && email.includes("@");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!valid) {
      return;
    }

    await updateProfile({
      avatarUrl: avatarUrl.trim() || undefined,
      email: email.trim(),
      nickname: nickname.trim(),
    });
  }

  return (
    <form className="space-y-5" onSubmit={handleSubmit}>
      <div>
        <h2 className="text-base font-semibold">{t("profile")}</h2>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          {t("profileDescription")}
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-[120px_1fr]">
        <div className="flex size-20 items-center justify-center rounded-2xl border bg-[#f7f7f5] text-xl font-semibold">
          {avatarUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              alt={nickname || t("profile")}
              className="size-full rounded-2xl object-cover"
              src={avatarUrl}
            />
          ) : (
            nickname.slice(0, 1).toUpperCase() || "W"
          )}
        </div>
        <div className="grid gap-3">
          <label className="space-y-1">
            <span className="text-xs font-medium">{t("nickname")}</span>
            <input
              className="w-full rounded-md border px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
              onChange={(event) => setNickname(event.target.value)}
              placeholder="WebAgent User"
              value={nickname}
            />
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium">{t("email")}</span>
            <input
              className="w-full rounded-md border px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
              onChange={(event) => setEmail(event.target.value)}
              placeholder="user@example.com"
              type="email"
              value={email}
            />
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium">{t("avatarUrl")}</span>
            <input
              className="w-full rounded-md border px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
              onChange={(event) => setAvatarUrl(event.target.value)}
              placeholder="https://example.com/avatar.png"
              type="url"
              value={avatarUrl}
            />
          </label>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 border-t pt-4">
        <div className="text-xs text-muted-foreground">
          {savedAt ? t("saved") : dirty ? t("unsavedChanges") : t("upToDate")}
        </div>
        <button
          className="flex h-9 items-center gap-2 rounded-md bg-[#242424] px-3 text-sm font-medium text-white hover:bg-[#111] disabled:opacity-40"
          disabled={!dirty || !valid || saving}
          type="submit"
        >
          {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
          {t("save")}
        </button>
      </div>
    </form>
  );
}
