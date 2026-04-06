import {
  AfterViewInit, ChangeDetectionStrategy, Component,
  CUSTOM_ELEMENTS_SCHEMA, DestroyRef, ElementRef,
  HostListener, inject, signal, ViewChild
} from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { AppManifest, AppRegistryService } from '../services/app-registry.service';

@Component({
  selector: 'app-shell',
  standalone: true,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (loading()) {
      <p class="status">Cargando...</p>
    }
    @if (error()) {
      <p class="status error">{{ error() }}</p>
    }
    <div #elementHost></div>
  `,
  styles: [`
    .status { padding: 24px; color: #666; font-size: 14px; }
    .error { color: #f88; }
  `]
})
export class AppShellComponent implements AfterViewInit {
  @ViewChild('elementHost') private hostRef!: ElementRef<HTMLElement>;

  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private registry = inject(AppRegistryService);
  private destroyed = false;

  loading = signal(true);
  error = signal('');

  constructor() {
    inject(DestroyRef).onDestroy(() => { this.destroyed = true; });
  }

  @HostListener('app-navigate', ['$event'])
  onNavigate(e: Event) {
    this.router.navigate([(e as CustomEvent).detail]);
  }

  async ngAfterViewInit() {
    const appId = this.route.snapshot.paramMap.get('appId')!;
    const manifest = await this.waitForManifest(appId);

    if (!manifest?.scriptUrl || !manifest.elementTag) {
      this.error.set(`App "${appId}" is not registered or has no frontend.`);
      this.loading.set(false);
      return;
    }

    try {
      await this.loadScript(manifest.scriptUrl);
      if (this.destroyed) return;
      const el = document.createElement(manifest.elementTag);
      this.hostRef.nativeElement.appendChild(el);
    } catch (e: any) {
      if (!this.destroyed) this.error.set(`Failed to load "${appId}": ${e.message}`);
    }
    if (!this.destroyed) this.loading.set(false);
  }

  private async waitForManifest(appId: string): Promise<AppManifest | null> {
    const timeoutMs = 6000;
    const pollIntervalMs = 100;
    const startedAt = Date.now();

    while (!this.destroyed && Date.now() - startedAt < timeoutMs) {
      const manifest = (this.registry.apps.value() ?? []).find(a => a.id === appId);
      if (manifest) return manifest;

      if (!this.registry.apps.isLoading()) break;
      await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
    }

    return (this.registry.apps.value() ?? []).find(a => a.id === appId) ?? null;
  }

  private loadScript(src: string): Promise<void> {
    return new Promise((resolve, reject) => {
      if (document.querySelector(`script[src="${src}"]`)) { resolve(); return; }
      const script = document.createElement('script');
      script.src = src;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error(`Cannot load ${src}`));
      document.head.appendChild(script);
    });
  }
}
