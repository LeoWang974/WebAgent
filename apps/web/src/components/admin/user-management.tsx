"use client";

import { FormEvent, useEffect, useState } from "react";
import { Check, KeyRound, Loader2, Plus, Search, Trash2, Users, X } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { webAgentApi } from "@/services";
import { useUserStore } from "@/stores";
import type { User } from "@/types";

export function UserManagement() {
  const { t } = useI18n();
  const currentUser = useUserStore((state) => state.user);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | undefined>();
  const [filterRole, setFilterRole] = useState<"all" | "admin" | "user">("all");
  const [loading, setLoading] = useState(false);
  const [nickname, setNickname] = useState("");
  const [password, setPassword] = useState("");
  const [resettingUserId, setResettingUserId] = useState<string | undefined>();
  const [resetPassword, setResetPassword] = useState("");
  const [role, setRole] = useState<"admin" | "user">("user");
  const [search, setSearch] = useState("");
  const [saving, setSaving] = useState(false);
  const [username, setUsername] = useState("");
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

  const filteredUsers = users.filter((user) => {
    const matchesRole = filterRole === "all" || user.role === filterRole;
    const keyword = search.trim().toLowerCase();
    const matchesSearch =
      !keyword ||
      user.nickname.toLowerCase().includes(keyword) ||
      user.email.toLowerCase().includes(keyword) ||
      (user.username ?? "").toLowerCase().includes(keyword) ||
      user.id.toLowerCase().includes(keyword);
    return matchesRole && matchesSearch;
  });

  function formatDate(value?: string) {
    if (!value) {
      return "-";
    }
    return new Intl.DateTimeFormat("zh-CN", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(value));
  }

  async function handleCreateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim() || password.length < 4) {
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
        username: username.trim() || undefined,
      });
      setUsers((items) => [user, ...items]);
      setEmail("");
      setNickname("");
      setPassword("");
      setRole("user");
      setUsername("");
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

  async function handleResetPassword(userId: string) {
    if (resetPassword.length < 4) {
      setError(t("passwordValidation"));
      return;
    }

    setError(undefined);
    try {
      const updatedUser = await webAgentApi.resetUserPassword(userId, resetPassword);
      setUsers((items) => items.map((user) => (user.id === userId ? updatedUser : user)));
      setResettingUserId(undefined);
      setResetPassword("");
    } catch (resetError) {
      setError(resetError instanceof Error ? resetError.message : "Failed to reset password.");
    }
  }

  return (
    <div className="space-y-4">
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
        className="grid gap-2 rounded-lg border border-[#ece9e1] bg-[#fbfbfa] p-3 md:grid-cols-2 xl:grid-cols-[minmax(180px,1.2fr)_minmax(140px,1fr)_minmax(140px,1fr)_minmax(140px,1fr)_140px_112px]"
        onSubmit={handleCreateUser}
      >
        <input
          className="h-9 min-w-0 rounded-md border bg-white px-3 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
          onChange={(event) => setEmail(event.target.value)}
          placeholder={t("email")}
          type="email"
          value={email}
        />
        <input
          className="h-9 min-w-0 rounded-md border bg-white px-3 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
          onChange={(event) => setNickname(event.target.value)}
          placeholder={t("nickname")}
          value={nickname}
        />
        <input
          className="h-9 min-w-0 rounded-md border bg-white px-3 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
          onChange={(event) => setUsername(event.target.value)}
          pattern="[A-Za-z0-9_.-]{3,80}"
          placeholder={t("username")}
          value={username}
        />
        <input
          className="h-9 min-w-0 rounded-md border bg-white px-3 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
          minLength={4}
          onChange={(event) => setPassword(event.target.value)}
          placeholder={t("password")}
          type="password"
          value={password}
        />
        <select
          className="h-9 min-w-0 rounded-md border bg-white px-2 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
          onChange={(event) => setRole(event.target.value as "admin" | "user")}
          value={role}
        >
          <option value="user">{t("normalUser")}</option>
          <option value="admin">{t("adminUser")}</option>
        </select>
        <button
          className="flex h-9 items-center justify-center gap-2 rounded-md bg-[#242424] px-3 text-sm font-medium text-white disabled:opacity-40"
          disabled={saving || !email.trim() || password.length < 4}
          type="submit"
        >
          {saving ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
          {t("createUser")}
        </button>
      </form>

      {error ? <p className="text-xs text-red-600">{error}</p> : null}

      <div className="overflow-hidden rounded-lg border">
        <div className="flex flex-col gap-2 border-b bg-[#f7f7f5] px-3 py-2 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">{t("userList")}</span>
            <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-muted-foreground">
              {filteredUsers.length} / {users.length}
            </span>
            {loading ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : null}
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <label className="flex h-9 items-center gap-2 rounded-md border bg-white px-2 text-sm">
              <Search className="size-4 text-muted-foreground" />
              <input
                className="w-full bg-transparent outline-none sm:w-48"
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t("search")}
                value={search}
              />
            </label>
            <select
              className="h-9 min-w-[128px] rounded-md border bg-white px-2 text-sm outline-none"
              onChange={(event) => setFilterRole(event.target.value as "all" | "admin" | "user")}
              value={filterRole}
            >
              <option value="all">{t("allRoles")}</option>
              <option value="admin">{t("adminUser")}</option>
              <option value="user">{t("normalUser")}</option>
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] table-fixed border-collapse text-left text-sm">
            <colgroup>
              <col className="w-[25%]" />
              <col className="w-[23%]" />
              <col className="w-[9%]" />
              <col className="w-[8%]" />
              <col className="w-[7%]" />
              <col className="w-[13%]" />
              <col className="w-[15%]" />
            </colgroup>
            <thead className="bg-white text-xs text-muted-foreground">
              <tr className="border-b">
                <th className="px-3 py-2 font-medium">{t("username")}</th>
                <th className="px-3 py-2 font-medium">{t("email")}</th>
                <th className="px-3 py-2 font-medium">{t("role")}</th>
                <th className="px-3 py-2 font-medium">{t("passwordMask")}</th>
                <th className="px-3 py-2 font-medium">{t("conversationCount")}</th>
                <th className="px-3 py-2 font-medium">{t("createdAt")}</th>
                <th className="px-3 py-2 text-right font-medium">{t("actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y bg-white">
              {filteredUsers.map((user) => {
                const isSelf = user.id === currentUser?.id;
                return (
                  <tr className="align-middle hover:bg-[#fbfbfa]" key={user.id}>
                    <td className="px-3 py-2">
                      <div className="truncate font-medium">{user.nickname}</div>
                      <div className="truncate text-xs text-muted-foreground">
                        @{user.username ?? "-"} · {user.id}
                      </div>
                    </td>
                    <td className="truncate px-3 py-2 text-muted-foreground">{user.email}</td>
                    <td className="px-3 py-2">
                      <span className="inline-flex max-w-full rounded-full border bg-[#f7f7f5] px-2 py-0.5 text-xs text-muted-foreground">
                        {user.role === "admin" ? t("adminUser") : t("normalUser")}
                      </span>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                      {user.passwordMask ?? "********"}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {user.conversationCount ?? 0}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {formatDate(user.createdAt)}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex justify-end gap-1.5">
                        {resettingUserId === user.id ? (
                          <div className="flex items-center justify-end gap-1.5">
                            <input
                              autoFocus
                              className="h-8 w-28 rounded-md border px-2 text-xs outline-none focus:border-[#242424]"
                              minLength={4}
                              onChange={(event) => setResetPassword(event.target.value)}
                              placeholder={t("newPassword")}
                              type="password"
                              value={resetPassword}
                            />
                            <button
                              className="flex size-8 items-center justify-center rounded-md bg-[#242424] text-white hover:bg-[#111] disabled:opacity-40"
                              disabled={resetPassword.length < 4}
                              onClick={() => void handleResetPassword(user.id)}
                              title={t("save")}
                              type="button"
                            >
                              <Check className="size-3.5" />
                            </button>
                            <button
                              className="flex size-8 items-center justify-center rounded-md border text-muted-foreground hover:bg-[#f7f7f5]"
                              onClick={() => {
                                setResettingUserId(undefined);
                                setResetPassword("");
                              }}
                              title={t("cancel")}
                              type="button"
                            >
                              <X className="size-3.5" />
                            </button>
                          </div>
                        ) : (
                          <>
                            <button
                              className="flex size-8 items-center justify-center rounded-md border border-[#dfe3ea] bg-white text-muted-foreground transition hover:border-[#b8c0cc] hover:bg-[#f7f7f5] hover:text-foreground"
                              onClick={() => {
                                setResettingUserId(user.id);
                                setResetPassword("");
                              }}
                              title={t("resetPassword")}
                              type="button"
                            >
                              <KeyRound className="size-3.5" />
                            </button>
                            <button
                              className="flex size-8 items-center justify-center rounded-md border border-[#f0d6d6] bg-white text-[#a15c5c] transition hover:border-[#dfb5b5] hover:bg-[#fff7f7] disabled:border-[#e5e5e0] disabled:text-muted-foreground disabled:opacity-40"
                              disabled={isSelf}
                              onClick={() => void handleDeleteUser(user.id)}
                              title={isSelf ? t("deleteSelfNotAllowed") : t("deleteUser")}
                              type="button"
                            >
                              <Trash2 className="size-3.5" />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {filteredUsers.length === 0 ? (
          <div className="border-t bg-white px-3 py-8 text-center text-sm text-muted-foreground">
            {t("noUsersFound")}
          </div>
        ) : null}
      </div>
    </div>
  );
}
