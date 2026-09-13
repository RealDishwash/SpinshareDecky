import { callable } from '@decky/api';
import { Filters, Song, Status } from './types';

export const browse = callable<[string, string, number, Filters], {
  songs: Song[]; hasMore: boolean; total: number | null;
}>('browse');
export const detail = callable<[number], Song>('detail');
export const status = callable<[], Status>('status');
export const install = callable<[number], boolean>('install');
export const remove = callable<[string], { message: string }>('delete_song');
export const setPath = callable<[string], Status>('set_path');

export function errorMessage(error: unknown): string {
  if (error && typeof error === 'object') {
    const value = error as { message?: string; pythonTraceback?: string };
    if (value.message) return value.message;
    if (value.pythonTraceback) return value.pythonTraceback.trim().split('\n').pop()!;
  }
  return String(error) || 'Request failed. Check your connection and try again.';
}
