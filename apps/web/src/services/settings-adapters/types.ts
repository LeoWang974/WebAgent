import type {
  DataContextSettings,
  InterfaceSettings,
  ModelConfig,
  Skill,
  SkillKey,
  User,
} from "@/types";
import type { AuthResult } from "../adapters/types";

export type ProfileUpdateInput = Pick<User, "avatarUrl" | "email" | "nickname" | "username">;

export interface PasswordUpdateInput {
  currentPassword: string;
  newPassword: string;
  relogin?: boolean;
}

export type PasswordUpdateResult = AuthResult | null | undefined;

export type ModelCreateInput = Omit<
  ModelConfig,
  "id" | "isAvailable" | "isDefault"
>;

export interface SettingsApiAdapter {
  addModel(input: ModelCreateInput): Promise<ModelConfig>;
  deleteModel(modelId: string): Promise<void>;
  getDataContextSettings(): Promise<DataContextSettings>;
  getInterfaceSettings(): Promise<InterfaceSettings>;
  setDefaultModel(modelId: string): Promise<ModelConfig[]>;
  setDefaultSkill(skillKey: SkillKey): Promise<Skill[]>;
  testModelConnection(modelId: string): Promise<ModelConfig>;
  toggleSkillEnabled(skillKey: SkillKey): Promise<Skill[]>;
  updateDataContextSettings(
    input: DataContextSettings,
  ): Promise<DataContextSettings>;
  updateInterfaceSettings(input: InterfaceSettings): Promise<InterfaceSettings>;
  updateModel(
    modelId: string,
    input: Partial<ModelConfig>,
  ): Promise<ModelConfig>;
  updateProfile(input: ProfileUpdateInput): Promise<User>;
  updatePassword(input: PasswordUpdateInput): Promise<PasswordUpdateResult>;
  updateSkillVersion(
    skillKey: SkillKey,
    direction: "rollback" | "update",
  ): Promise<Skill[]>;
}
