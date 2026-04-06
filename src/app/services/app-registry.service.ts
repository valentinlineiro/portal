import { Injectable, resource } from '@angular/core';

export interface AppManifest {
  id: string;
  name: string;
  description: string;
  route: string;
  icon: string;
  status: 'stable' | 'wip' | 'disabled';
  backend: { pathPrefix: string } | null;
  scriptUrl?: string;
  elementTag?: string;
}

@Injectable({ providedIn: 'root' })
export class AppRegistryService {
  readonly apps = resource<AppManifest[], unknown>({
    loader: () => fetch('/api/registry').then(r => r.json()) as Promise<AppManifest[]>
  });
}
