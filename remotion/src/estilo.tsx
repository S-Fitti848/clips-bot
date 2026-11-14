// El ESTILO NUEVO de Así Nació, en un solo lugar (Santi, 2026-11-14: "cartoon con volumen").
//
// - Contorno de grosor variable: cada forma lleva una copia oscura corrida hacia abajo-derecha (lado de
//   la sombra) debajo del relleno y un trazo fino encima: el borde es fino arriba-izquierda (de donde
//   viene la luz) y grueso abajo-derecha. Nada de trazos de grosor parejo "de vector".
// - Sombra propia en DOS pasos de color plano (medio y oscuro), en una media luna abajo-derecha de cada
//   forma, recortada a la forma: volumen de dibujo animado, sin degradés "de IA".
// - Brillo: una elipse clara y chica arriba-izquierda (solo donde hace falta: cabezas, objetos).
// - Sombra de contacto en el piso (elipse con un degradé radial MUY suave): los personajes pisan.
// - Colores: la paleta del motor actual (paleta.py), así el canal sigue reconociéndose.
import React, {useId} from 'react';

export const C = '#1f1a24'; // contorno (casi negro, un poco violeta)
export const ANCHO = 1080;
export const ALTO = 1920;

export const P = {
  rojo: '#ef5a4c', naranja: '#f59a3a', amarillo: '#ffd23f', verde: '#4cb963', turquesa: '#2ec4b6',
  azul: '#3a86ff', violeta: '#8b5cf6', rosa: '#ff7aa8', blanco: '#fffaf0', gris: '#9aa0ab',
  grisOscuro: '#5b6170', madera: '#a8714a', maderaOscura: '#7a4b2a', cielo: '#8fd3ff', cieloBajo: '#c9ecff',
  vidrio: '#9fe3ff', crema: '#f2ece0', oro: '#e8b53a', oroOscuro: '#b07d1c',
};

// ---- color ---------------------------------------------------------------------------------------
const hex = (h: string): [number, number, number] => {
  const c = h.replace('#', '');
  if (c.length !== 6) return [128, 128, 128];
  return [parseInt(c.slice(0, 2), 16), parseInt(c.slice(2, 4), 16), parseInt(c.slice(4, 6), 16)];
};
export const mezclar = (a: string, b: string, f: number): string => {
  if (!a.startsWith('#') || a.length !== 7) return a;
  const x = hex(a);
  const y = hex(b);
  return '#' + x.map((v, i) => Math.round(v + (y[i] - v) * f).toString(16).padStart(2, '0')).join('');
};
// la sombra tira a violeta (no a negro): más "dibujo", menos "barro"
export const sombra = (c: string) => mezclar(c, '#3b2d63', 0.24);
export const sombraFuerte = (c: string) => mezclar(c, '#2a1f4d', 0.4);
export const luz = (c: string) => mezclar(c, '#fffbe8', 0.5);

export const useClipId = () => 'k' + useId().replace(/[^a-zA-Z0-9]/g, '');

// ---- formas --------------------------------------------------------------------------------------
type FormaProps = {
  d: string;
  fill: string;
  b?: number; // grosor base del contorno
  sd?: number; // ancho de la media luna de sombra
  brillo?: [number, number, number, number] | null; // cx, cy, rx, ry
  sinSombra?: boolean;
  children?: React.ReactNode; // detalles adentro (recortados a la forma)
  opacity?: number;
};

export const Forma: React.FC<FormaProps> = ({d, fill, b = 7, sd = 12, brillo, sinSombra, children, opacity}) => {
  const id = useClipId();
  const conClip = !sinSombra || brillo || children;
  return (
    <g opacity={opacity}>
      <path d={d} fill={C} stroke={C} strokeWidth={b * 1.5} strokeLinejoin="round" transform="translate(1.6 2.4)" />
      <path d={d} fill={fill} />
      {conClip ? (
        <>
          <clipPath id={id}>
            <path d={d} />
          </clipPath>
          <g clipPath={`url(#${id})`}>
            {!sinSombra ? (
              <>
                <rect x={-4000} y={-4000} width={8000} height={8000} fill={sombraFuerte(fill)} />
                <path d={d} fill={sombra(fill)} transform={`translate(${-sd * 0.5} ${-sd * 0.55})`} />
                <path d={d} fill={fill} transform={`translate(${-sd} ${-sd * 1.1})`} />
              </>
            ) : null}
            {children}
            {brillo ? <ellipse cx={brillo[0]} cy={brillo[1]} rx={brillo[2]} ry={brillo[3]} fill={luz(fill)} opacity={0.6} /> : null}
          </g>
        </>
      ) : null}
      <path d={d} fill="none" stroke={C} strokeWidth={b * 0.75} strokeLinejoin="round" />
    </g>
  );
};

// círculo y rectángulo como caminos (para Forma)
export const dCirculo = (cx: number, cy: number, r: number) =>
  `M${cx - r} ${cy} A${r} ${r} 0 1 0 ${cx + r} ${cy} A${r} ${r} 0 1 0 ${cx - r} ${cy} Z`;
export const dElipse = (cx: number, cy: number, rx: number, ry: number) =>
  `M${cx - rx} ${cy} A${rx} ${ry} 0 1 0 ${cx + rx} ${cy} A${rx} ${ry} 0 1 0 ${cx - rx} ${cy} Z`;
export const dRect = (x: number, y: number, w: number, h: number, r = 0) => {
  if (!r) return `M${x} ${y} H${x + w} V${y + h} H${x} Z`;
  r = Math.min(r, w / 2, h / 2);
  return `M${x + r} ${y} H${x + w - r} Q${x + w} ${y} ${x + w} ${y + r} V${y + h - r} Q${x + w} ${y + h} ${x + w - r} ${y + h} H${x + r} Q${x} ${y + h} ${x} ${y + h - r} V${y + r} Q${x} ${y} ${x + r} ${y} Z`;
};

// Un miembro (brazo, pierna): línea gruesa con contorno variable, sombra del lado de abajo y un brillo
// fino del de arriba. Los corrimientos son menores que medio ancho: nunca se salen del miembro.
export const Miembro: React.FC<{pts: [number, number][]; color: string; ancho: number; b?: number}> = ({pts, color, ancho, b = 7}) => {
  const d = 'M' + pts.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(' L');
  const comun = {fill: 'none', strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const};
  return (
    <g>
      <path d={d} {...comun} stroke={C} strokeWidth={ancho + b * 1.6} transform="translate(1.6 2.4)" />
      <path d={d} {...comun} stroke={C} strokeWidth={ancho + b * 0.9} />
      <path d={d} {...comun} stroke={color} strokeWidth={ancho} />
      <path d={d} {...comun} stroke={sombra(color)} strokeWidth={ancho * 0.4} transform={`translate(${ancho * 0.2} ${ancho * 0.2})`} />
      <path d={d} {...comun} stroke={luz(color)} strokeWidth={ancho * 0.16} opacity={0.55} transform={`translate(${-ancho * 0.24} ${-ancho * 0.2})`} />
    </g>
  );
};

// Línea de detalle (costuras, pliegues, mechones): fina y con poca opacidad.
export const Linea: React.FC<{d: string; w?: number; o?: number; color?: string}> = ({d, w = 4, o = 0.35, color = C}) => (
  <path d={d} fill="none" stroke={color} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" opacity={o} />
);

// Las definiciones compartidas de cada capa (degradés suaves de piso, pared y sombra de contacto).
export const Defs: React.FC = () => (
  <defs>
    <radialGradient id="contacto">
      <stop offset="0" stopColor="#1a1030" stopOpacity="0.42" />
      <stop offset="0.7" stopColor="#1a1030" stopOpacity="0.18" />
      <stop offset="1" stopColor="#1a1030" stopOpacity="0" />
    </radialGradient>
    <linearGradient id="vinieta" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stopColor="#000" stopOpacity="0.18" />
      <stop offset="0.25" stopColor="#000" stopOpacity="0" />
      <stop offset="0.8" stopColor="#000" stopOpacity="0" />
      <stop offset="1" stopColor="#000" stopOpacity="0.22" />
    </linearGradient>
    <linearGradient id="luzVentana" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stopColor="#fff6d0" stopOpacity="0.32" />
      <stop offset="1" stopColor="#fff6d0" stopOpacity="0" />
    </linearGradient>
  </defs>
);

// Sombra de contacto en el piso, en coordenadas del mundo (no salta con el personaje).
export const SombraPiso: React.FC<{x: number; y: number; ancho: number; altura?: number}> = ({x, y, ancho, altura = 0}) => {
  const k = Math.max(0.35, 1 - altura / 700);
  return <ellipse cx={x} cy={y + 4} rx={ancho * k} ry={ancho * 0.16 * k} fill="url(#contacto)" />;
};
