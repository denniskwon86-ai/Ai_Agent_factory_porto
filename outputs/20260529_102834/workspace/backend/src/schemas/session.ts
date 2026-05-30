import { z } from 'zod';

export const createSessionSchema = z.object({
  name: z.string().min(1, 'Session name is required'),
  storage_path: z.string().min(1, 'Storage path is required'),
  compression: z.boolean().optional().default(false),
  encryption: z.boolean().optional().default(false),
});

export const updateSessionSchema = createSessionSchema.partial();

export const sessionItemSchema = z.object({
  item_path: z.string().min(1, 'Item path is required'),
  item_type: z.string().min(1, 'Item type is required'),
});

export const createSessionWithItemsSchema = createSessionSchema.extend({
  items: z.array(sessionItemSchema).optional(),
});

export const recoveryLogSchema = z.object({
  item_path: z.string().min(1, 'Item path is required'),
  action_type: z.string().min(1, 'Action type is required'),
  status: z.string().min(1, 'Status is required'),
  started_at: z.string().datetime(),
  completed_at: z.string().datetime().optional(),
  error_message: z.string().optional(),
});

export const createRecoveryLogSchema = recoveryLogSchema.omit({ completed_at: true, error_message: true }).extend({
  completed_at: z.string().datetime().optional(),
  error_message: z.string().optional(),
});

export type CreateSessionInput = z.infer<typeof createSessionSchema>;
export type UpdateSessionInput = z.infer<typeof updateSessionSchema>;
export type SessionItemInput = z.infer<typeof sessionItemSchema>;
export type CreateSessionWithItemsInput = z.infer<typeof createSessionWithItemsSchema>;
export type RecoveryLogInput = z.infer<typeof recoveryLogSchema>;
export type CreateRecoveryLogInput = z.infer<typeof createRecoveryLogSchema>;