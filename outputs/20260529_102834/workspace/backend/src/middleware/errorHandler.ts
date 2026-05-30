import { Request, Response, NextFunction } from 'express';
import { ZodError } from 'zod';

export const errorHandler = (err: Error, req: Request, res: Response, next: NextFunction) => {
  console.error(err.stack);

  if (err instanceof ZodError) {
    return res.status(400).json({
      message: 'Validation error',
      errors: err.errors.map((e: any) => ({
        path: e.path.join('.'),
        message: e.message,
      })),
    });
  }

  // Handle specific known errors or general server errors
  const statusCode = (err as any).statusCode || 500;
  const message = (err as any).message || 'Internal Server Error';

  res.status(statusCode).json({
    message: message,
  });
};