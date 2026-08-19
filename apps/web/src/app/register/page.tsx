/**
 * File purpose: Defines the Next.js page route or route layout.
 * Main declarations: RegisterPage handles register page.
 */

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Loader2, UserPlus } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { useUserStore } from "@/stores";

export default function RegisterPage() {
  const { t } = useI18n();
  const router = useRouter();
  const register = useUserStore((state) => state.register);
  const saving = useUserStore((state) => state.saving);
  const error = useUserStore((state) => state.error);
  const [email, setEmail] = useState("");
  const [nickname, setNickname] = useState("");
  const [password, setPassword] = useState("");
  const [username, setUsername] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedEmail = email.trim();
    const ok = await register({
      email: normalizedEmail || undefined,
      nickname: nickname.trim() || undefined,
      password,
      username: username.trim() || undefined,
    });
    if (ok) {
      router.replace("/app");
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f7f7f4] p-6">
      <form
        className="w-full max-w-sm rounded-lg border border-[#deded8] bg-white p-6 shadow-sm"
        onSubmit={handleSubmit}
      >
        <div className="mb-6">
          <div className="mb-3 flex size-9 items-center justify-center rounded-md bg-[#242424] text-sm font-semibold text-white">
            W
          </div>
          <h1 className="text-lg font-semibold">{t("signUpTitle")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("signUpDescription")}
          </p>
        </div>

        <div className="space-y-3">
          <label className="block space-y-1.5">
            <span className="text-xs font-medium">{t("nickname")}</span>
            <input
              autoComplete="nickname"
              className="h-10 w-full rounded-md border px-3 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
              onChange={(event) => setNickname(event.target.value)}
              placeholder="WebAgent User"
              value={nickname}
            />
          </label>
          <label className="block space-y-1.5">
            <span className="text-xs font-medium">{t("username")}</span>
            <input
              autoComplete="username"
              className="h-10 w-full rounded-md border px-3 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
              onChange={(event) => setUsername(event.target.value)}
              pattern="[A-Za-z0-9_.-]{3,80}"
              placeholder="test"
              required
              value={username}
            />
          </label>
          <label className="block space-y-1.5">
            <span className="text-xs font-medium">{t("email")}（可选）</span>
            <input
              autoComplete="email"
              className="h-10 w-full rounded-md border px-3 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@example.com"
              type="email"
              value={email}
            />
          </label>
          <label className="block space-y-1.5">
            <span className="text-xs font-medium">{t("password")}</span>
            <input
              autoComplete="new-password"
              className="h-10 w-full rounded-md border px-3 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
              minLength={4}
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </label>
        </div>

        {error ? <p className="mt-3 text-xs text-red-600">{error}</p> : null}

        <button
          className="mt-5 flex h-10 w-full items-center justify-center gap-2 rounded-md bg-[#242424] text-sm font-medium text-white hover:bg-[#111] disabled:opacity-50"
          disabled={saving}
          type="submit"
        >
          {saving ? <Loader2 className="size-4 animate-spin" /> : <UserPlus className="size-4" />}
          {t("signUp")}
        </button>

        <p className="mt-4 text-center text-xs text-muted-foreground">
          {t("alreadyHaveAccount")}{" "}
          <Link className="font-medium text-foreground hover:underline" href="/login">
            {t("signIn")}
          </Link>
        </p>
      </form>
    </main>
  );
}
