"use client";

import { FormEvent, useEffect, useState } from "react";
import { Loader2, Plus, Trash2, Users } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { webAgentApi } from "@/services";
import { useUserStore } from "@/stores";
import type { User } from "@/types";

export function UserManagement() {
  const { t } = useI18n();
  const currentUser = useUserStore((state) => state.user);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const [nickname, setNickname] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "user">("user");
  const [saving, setSaving] = useState(false);
  const [users, setUsers] = useState<User[]>([]);

  async function loadUsers() {
    setError(undefined);
    setLoading(true);
    try {
      setUsers(await webAgentApi.listUsers());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load users.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadUsers();
  }, []);

  async function handleCreateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim() || password.length < 6) {
      return;
    }

    setError(undefined);
    setSaving(true);
    try {
      const user = await webAgentApi.createUser({
        email: email.trim(),
        nickname: nickname.trim() || undefined,
        password,
        role,
      });
      setUsers((items) => [user, ...items]);
      setEmail("");
      setNickname("");
      setPassword("");
      setRole("user");
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Failed to create user.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteUser(userId: string) {
    setError(undefined);
    try {
      await webAgentApi.deleteUser(userId);
      setUsers((items) => items.filter((user) => user.id !== userId));
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Failed to delete user.");
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{t("userManagement")}</h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            {t("userManagementDescription")}
          </p>
        </div>
        <div className="flex size-9 items-center justify-center rounded-md border bg-[#f7f7f5]">
          <Users className="size-4" />
        </div>
      </div>

      <form
        className="grid gap-3 rounded-lg border border-[#ece9e1] bg-[#fbfbfa] p-3 md:grid-cols-[1fr_1fr_1fr_130px_auto]"
        onSubmit={handleCreateUser}
      >
        <input
          className="h-9 rounded-md border bg-white px-3 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
          onChange={(event) => setEmail(event.target.value)}
          placeholder={t("email")}
          type="email"
          value={email}
        />
        <input
          className="h-9 rounded-md border bg-white px-3 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
          onChange={(event) => setNickname(event.target.value)}
          placeholder={t("nickname")}
          value={nickname}
        />
        <input
          className="h-9 rounded-md border bg-white px-3 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
          minLength={6}
          onChange={(event) => setPassword(event.target.value)}
          placeholder={t("password")}
          type="password"
          value={password}
        />
        <select
          className="h-9 rounded-md border bg-white px-2 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
          onChange={(event) => setRole(event.target.value as "admin" | "user")}
          value={role}
        >
          <option value="user">{t("normalUser")}</option>
          <option value="admin">{t("adminUser")}</option>
        </select>
        <button
          className="flex h-9 items-center justify-center gap-2 rounded-md bg-[#242424] px-3 text-sm font-medium text-white disabled:opacity-40"
          disabled={saving || !email.trim() || password.length < 6}
          type="submit"
        >
          {saving ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
          {t("createUser")}
        </button>
      </form>

      {error ? <p className="text-xs text-red-600">{error}</p> : null}

      <div className="overflow-hidden rounded-lg border">
        <div className="flex items-center justify-between border-b bg-[#f7f7f5] px-3 py-2">
          <span className="text-sm font-medium">{t("userList")}</span>
          {loading ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : null}
        </div>
        <div className="divide-y">
          {users.map((user) => {
            const isSelf = user.id === currentUser?.id;
            return (
              <div className="grid gap-3 px-3 py-3 text-sm md:grid-cols-[1fr_1fr_120px_auto]" key={user.id}>
                <div className="min-w-0">
                  <div className="truncate font-medium">{user.nickname}</div>
                  <div className="truncate text-xs text-muted-foreground">{user.id}</div>
                </div>
                <div className="truncate text-muted-foreground">{user.email}</div>
                <div className="text-muted-foreground">
                  {user.role === "admin" ? t("adminUser") : t("normalUser")}
                </div>
                <button
                  className="flex h-8 items-center justify-center gap-1.5 rounded-md border px-2 text-xs text-muted-foreground hover:bg-[#f7f7f5] disabled:opacity-40"
                  disabled={isSelf}
                  onClick={() => void handleDeleteUser(user.id)}
                  title={isSelf ? t("deleteSelfNotAllowed") : t("deleteUser")}
                  type="button"
                >
                  <Trash2 className="size-3.5" />
                  {t("deleteUser")}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
