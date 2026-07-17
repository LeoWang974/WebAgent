import type {
  DataContextSettings,
  ModelConfig,
  Skill,
  SkillKey,
  User,
} from "@/types";

export type ProfileUpdateInput = Pick<User, "avatarUrl" | "email" | "nickname" | "username">;

export interface PasswordUpdateInput {
  currentPassword: string;
  newPassword: string;
}

export type ModelCreateInput = Omit<
  ModelConfig,
  "id" | "isAvailable" | "isDefault"
>;

export interface SettingsApiAdapter {
  addModel(input: ModelCreateInput): Promise<ModelConfig>;
  deleteModel(modelId: string): Promise<void>;
  getDataContextSettings(): Promise<DataContextSettings>;
  setDefaultModel(modelId: string): Promise<ModelConfig[]>;
  setDefaultSkill(skillKey: SkillKey): Promise<Skill[]>;
  testModelConnection(modelId: string): Promise<ModelConfig>;
  toggleSkillEnabled(skillKey: SkillKey): Promise<Skill[]>;
  updateDataContextSettings(
    input: DataContextSettings,
  ): Promise<DataContextSettings>;
  updateModel(
    modelId: string,
    input: Partial<ModelConfig>,
  ): Promise<ModelConfig>;
  updateProfile(input: ProfileUpdateInput): Promise<User>;
  updatePassword(input: PasswordUpdateInput): Promise<void>;
  updateSkillVersion(
    skillKey: SkillKey,
    direction: "rollback" | "update",
  ): Promise<Skill[]>;
}
