import { Routes } from '@angular/router';

import { GeospatialPageComponent } from './pages/geospatial-page.component';

export const routes: Routes = [
  {
    path: '',
    component: GeospatialPageComponent,
    data: {
      title: 'AEGIS | Search workspace',
      description: 'Run location-aware geospatial searches and inspect verified map results in AEGIS.',
    },
  },
  {
    path: 'geodata',
    loadComponent: () => import('./pages/capabilities-page.component').then((m) => m.CapabilitiesPageComponent),
    data: {
      title: 'AEGIS | Geospatial catalog',
      description: 'Browse the manifest-backed geospatial providers, layers, map types, and direct tools available in AEGIS.',
    },
  },
  {
    path: 'settings',
    loadComponent: () => import('./pages/settings-page.component').then((m) => m.SettingsPageComponent),
    data: {
      title: 'AEGIS | Settings',
      description: 'Choose the AEGIS agent model and manage model and geospatial provider access.',
    },
  },
  { path: '**', redirectTo: '' },
];
