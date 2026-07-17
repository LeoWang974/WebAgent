"use client";

import { FormEvent, useEffect, useState } from "react";
import { KeyRound, Loader2, Plus, Search, Trash2, Users } from "lucide-react";
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
        className="grid gap-3 rounded-lg border border-[#ece9e1] bg-[#fbfbfa] p-3 md:grid-cols-[1fr_1fr_1fr_1fr_130px_auto]"
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
          onChange={(event) => setUsername(event.target.value)}
          pattern="[A-Za-z0-9_.-]{3,80}"
          placeholder={t("username")}
          value={username}
        />
        <input
          className="h-9 rounded-md border bg-white px-3 text-sm outline-none focus:ring-1 focus:ring-[#242424]"
          minLength={4}
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
          disabled={saving || !email.trim() || password.length < 4}
          type="submit"
        >
          {saving ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
          {t("createUser")}
        </button>
      </form>

      {error ? <p className="text-xs text-red-600">{error}</p> : null}

      <div className="overflow-hidden rounded-lg border">
        <div className="grid gap-3 border-b bg-[#f7f7f5] px-3 py-2 md:grid-cols-[1fr_auto_auto]">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">{t("userList")}</span>
            {loading ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : null}
          </div>
          <label className="flex h-9 items-center gap-2 rounded-md border bg-white px-2 text-sm">
            <Search className="size-4 text-muted-foreground" />
            <input
              className="w-48 bg-transparent outline-none"
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("search")}
              value={search}
            />
          </label>
          <select
            className="h-9 rounded-md border bg-white px-2 text-sm outline-none"
            onChange={(event) => setFilterRole(event.target.value as "all" | "admin" | "user")}
            value={filterRole}
          >
            <option value="all">{t("allRoles")}</option>
            <option value="admin">{t("adminUser")}</option>
            <option value="user">{t("normalUser")}</option>
          </select>
        </div>
        <div className="divide-y">
          {filteredUsers.map((user) => {
            const isSelf = user.id === currentUser?.id;
            return (
              <div className="grid gap-3 px-3 py-3 text-sm xl:grid-cols-[1.2fr_1.3fr_90px_90px_1fr_1fr_190px]" key={user.id}>
                <div className="min-w-0">
                  <div className="truncate font-medium">{user.nickname}</div>
                  <div className="truncate text-xs text-muted-foreground">{user.id}</div>
                </div>
                <div className="min-w-0">
                  <div className="truncate text-muted-foreground">{user.email}</div>
                  <div className="truncate text-xs text-muted-foreground">@{user.username ?? "-"}</div>
                </div>
                <div className="font-mono text-xs text-muted-foreground">
                  {user.passwordMask ?? "********"}
                </div>
                <div className="text-muted-foreground">
                  {user.role === "admin" ? t("adminUser") : t("normalUser")}
                </div>
                <div className="text-xs text-muted-foreground">
                  {t("conversationCount")}: {user.conversationCount ?? 0}
                </div>
                <div className="text-xs text-muted-foreground">
                  <div>{t("createdAt")}: {formatDate(user.createdAt)}</div>
                  <div>{t("updatedAt")}: {formatDate(user.updatedAt)}</div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {resettingUserId === user.id ? (
                    <>
                      <input
                        className="h-8 w-24 rounded-md border px-2 text-xs outline-none"
                        minLength={4}
                        onChange={(event) => setResetPassword(event.target.value)}
                        placeholder={t("newPassword")}
                        type="password"
                        value={resetPassword}
                      />
                      <button
                        className="h-8 rounded-md border px-2 text-xs hover:bg-[#f7f7f5]"
                        onClick={() => void handleResetPassword(user.id)}
                        type="button"
                      >
                        {t("save")}
                      </button>
                    </>
                  ) : (
                    <button
                      className="flex h-8 items-center gap-1.5 rounded-md border px-2 text-xs text-muted-foreground hover:bg-[#f7f7f5]"
                      onClick={() => {
                        setResettingUserId(user.id);
                        setResetPassword("");
                      }}
                      type="button"
                    >
                      <KeyRound className="size-3.5" />
                      {t("resetPassword")}
                    </button>
                  )}
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
              </div>
            );
          })}
          {filteredUsers.length === 0 ? (
            <div className="px-3 py-8 text-center text-sm text-muted-foreground">
              {t("noUsersFound")}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
