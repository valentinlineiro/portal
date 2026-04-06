import { Injectable, resource } from '@angular/core';

export interface AppManifest {
  id: string;
  name: string;
  description: string;
  route: string;
  icon: string;
  status: 'stable' | 'wip' | 'disabled';
  backend: { pathPrefix: string } | null;
}

@Injectable({ providedIn: 'root' })
export class AppRegistryService {
  readonly apps = resource<AppManifest[], unknown>({
    loader: async () => {
      const reg = await fetch('/apps/registry.json').then(r => r.json()) as { apps: string[] };
      return Promise.all(
        reg.apps.map(id =>
          fetch(`/apps/${id}/manifest.json`).then(r => r.json()) as Promise<AppManifest>
        )
      );
    }
  });
}
