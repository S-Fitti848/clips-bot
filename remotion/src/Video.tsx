// Un cuadro del video: las capas (fondo + cámara + elementos), la pausa de Tito en gris, el remolino del
// viaje en el tiempo, las transiciones, el sepia del pasado y los subtítulos. Todo sale de los datos del
// cuadro (exportar.py): acá no se decide nada de la historia, solo cómo se ve.
import React, {useEffect, useState} from 'react';
import {AbsoluteFill, continueRender, delayRender, staticFile, useCurrentFrame} from 'remotion';
import {ANCHO as W, ALTO as H, C, Defs, SombraPiso} from './estilo';
import {DefsFondo, Fondo} from './fondos';
import {Persona} from './Persona';
import {Prop} from './props';
import {Tito} from './Tito';
import type {Capa, Datos, Item} from './tipos';

const cache: Record<string, Promise<Datos>> = {};
export const cargar = (archivo: string): Promise<Datos> => {
  if (!cache[archivo]) cache[archivo] = fetch(staticFile(archivo)).then((r) => r.json());
  return cache[archivo];
};

const suave = (u: number) => 0.5 - 0.5 * Math.cos(Math.PI * Math.max(0, Math.min(1, u)));
const salida = (u: number) => 1 - Math.pow(1 - Math.max(0, Math.min(1, u)), 3);

const transformar = (it: {x: number; y: number; r: number; sx: number; sy: number}) =>
  `translate(${it.x} ${it.y}) rotate(${it.r}) scale(${it.sx} ${it.sy})`;

const ItemSvg: React.FC<{it: Item; datos: Datos}> = ({it, datos}) => {
  if (it.k === 's') return <g dangerouslySetInnerHTML={{__html: it.s}} />;
  const tr = transformar(it);
  if (it.k === 'p') {
    const p = datos.personajes[it.id];
    const vx = it.v ? it.v[0] : 0;
    return (
      <g>
        {Math.abs(vx) > 9 ? <LineasVelocidad x={it.x} y={it.y} vx={vx} s={Math.abs(it.sx)} /> : null}
        <g transform={tr} opacity={it.o}>
          <Persona p={p} e={it.e} />
        </g>
      </g>
    );
  }
  if (it.k === 't')
    return (
      <g transform={tr} opacity={it.o}>
        <Tito pose={it.pose} ap={it.ap} pa={it.pa} ag={it.ag} re={it.re} inc={it.inc} />
      </g>
    );
  const prop = <Prop n={it.n} p={it.p} legacy={it.l ? datos.legacy[it.l] : undefined} />;
  const vel = it.v ? Math.hypot(it.v[0], it.v[1]) : 0;
  return (
    <g>
      {vel > 16 && it.v
        ? [1, 2, 3].map((k) => (
            // estela: copias que se van apagando detrás de lo que vuela (como un smear de dibujo animado)
            <g key={k} transform={`translate(${-it.v![0] * 0.45 * k} ${-it.v![1] * 0.45 * k}) ${tr}`} opacity={it.o * (0.3 - 0.08 * k)}>
              {prop}
            </g>
          ))
        : null}
      {vel > 16 && it.v ? <Estela x={it.x} y={it.y} v={it.v} s={Math.abs(it.sx)} /> : null}
      <g transform={tr} opacity={it.o}>
        {prop}
      </g>
    </g>
  );
};

// Líneas de velocidad detrás de quien corre o lo que vuela.
const LineasVelocidad: React.FC<{x: number; y: number; vx: number; s: number}> = ({x, y, vx, s}) => {
  const dir = vx > 0 ? -1 : 1;
  return (
    <g opacity={Math.min(0.8, Math.abs(vx) / 30)}>
      {[-430, -330, -230].map((dy, i) => (
        <path key={i} d={`M${x + dir * 150 * s} ${y + dy * s} h${dir * (90 + i * 40) * s}`} stroke="#ffffff" strokeWidth={9} strokeLinecap="round" />
      ))}
      {[-430, -330, -230].map((dy, i) => (
        <path key={'c' + i} d={`M${x + dir * 150 * s} ${y + dy * s} h${dir * (90 + i * 40) * s}`} stroke={C} strokeWidth={3} strokeLinecap="round" opacity={0.5} />
      ))}
    </g>
  );
};

const Estela: React.FC<{x: number; y: number; v: [number, number]; s: number}> = ({x, y, v, s}) => {
  const n = Math.hypot(v[0], v[1]);
  const ux = v[0] / n;
  const uy = v[1] / n;
  return (
    <g opacity={0.7}>
      {[-50, 0, 50].map((o, i) => {
        const px = x - uy * o * s;
        const py = y + ux * o * s;
        return <path key={i} d={`M${px - ux * 90 * s} ${py - uy * 90 * s} L${px - ux * (90 + n * 3) * s} ${py - uy * (90 + n * 3) * s}`} stroke="#ffffff" strokeWidth={7} strokeLinecap="round" />;
      })}
    </g>
  );
};

// Las sombras de contacto van ANTES que todos los elementos (abajo de todo, sobre el piso).
const Sombras: React.FC<{items: Item[]}> = ({items}) => (
  <g>
    {items.map((it, i) => {
      if (it.k === 'p') return <SombraPiso key={i} x={it.x} y={it.piso} ancho={150 * Math.abs(it.sx)} altura={it.piso - it.y} />;
      if (it.k === 't') return <SombraPiso key={i} x={it.x} y={it.piso} ancho={190 * Math.abs(it.sx)} altura={it.piso - it.y} />;
      return null;
    })}
  </g>
);

const camara = ([z, dx, dy, rot]: [number, number, number, number]) =>
  `translate(${W / 2} ${H / 2}) rotate(${rot}) scale(${z}) translate(${-W / 2 - dx} ${-H / 2 - dy})`;

// Remolino del viaje en el tiempo: un túnel de franjas que gira detrás de la escena que se va (así no
// quedan esquinas negras cuando la escena gira).
const Remolino: React.FC<{t: number}> = ({t}) => (
  <g>
    <rect width={W} height={H} fill="#2a1f4d" />
    <g transform={`translate(${W / 2} ${H / 2}) rotate(${(t * 220) % 360})`}>
      {Array.from({length: 16}, (_, i) => (
        <path key={i} d={`M0 0 L${Math.cos((i * 22.5 * Math.PI) / 180) * 1400} ${Math.sin((i * 22.5 * Math.PI) / 180) * 1400} A1400 1400 0 0 1 ${Math.cos(((i * 22.5 + 11) * Math.PI) / 180) * 1400} ${Math.sin(((i * 22.5 + 11) * Math.PI) / 180) * 1400} Z`} fill={i % 2 ? '#4b3a86' : '#6d4fb0'} />
      ))}
    </g>
    <circle cx={W / 2} cy={H / 2} r={260} fill="#ffe9a8" opacity={0.35} />
  </g>
);

const IconoPausa: React.FC<{u: number}> = ({u}) => (
  <g transform={`translate(110 390) scale(${0.6 + 0.4 * u})`} opacity={u}>
    <circle r={72} fill={C} transform="translate(2 3)" />
    <circle r={70} fill="#ffffff" stroke={C} strokeWidth={5} />
    <rect x={-30} y={-36} width={20} height={72} rx={4} fill={C} />
    <rect x={10} y={-36} width={20} height={72} rx={4} fill={C} />
  </g>
);

const CapaSvg: React.FC<{capa: Capa; t: number; datos: Datos}> = ({capa, t, datos}) => {
  const u = capa.pausa ?? 0;
  const legacyFondo = datos.legacy['fondo:' + capa.f.join(':')];
  const fid = `gris${Math.round(u * 100)}`;
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{position: 'absolute', inset: 0}}>
      <Defs />
      <DefsFondo />
      {u > 0.001 ? (
        <defs>
          <filter id={fid} x={0} y={0} width={W} height={H} filterUnits="userSpaceOnUse">
            <feColorMatrix type="saturate" values={String(1 - 0.92 * u)} />
          </filter>
        </defs>
      ) : null}
      {capa.giro ? <Remolino t={t} /> : null}
      <g filter={u > 0.001 ? `url(#${fid})` : undefined}>
        <g transform={camara(capa.c)}>
          <Fondo f={capa.f} cam={capa.c} t={t} legacy={legacyFondo} />
          <Sombras items={capa.fr} />
          {capa.fr.map((it, i) => <ItemSvg key={i} it={it} datos={datos} />)}
        </g>
        {capa.fi.map((it, i) => <ItemSvg key={'f' + i} it={it} datos={datos} />)}
      </g>
      {u > 0.001 ? (
        <>
          <rect width={W} height={H} fill="#4a4f5c" opacity={0.38 * u} />
          <IconoPausa u={u} />
        </>
      ) : null}
      {capa.en.map((it, i) => <ItemSvg key={'e' + i} it={it} datos={datos} />)}
    </svg>
  );
};

const Transicion: React.FC<{tipo: string; u: number; sale: React.ReactNode; entra: React.ReactNode}> = ({tipo, u, sale, entra}) => {
  if (tipo === 'fundido')
    return (
      <>
        <AbsoluteFill>{sale}</AbsoluteFill>
        <AbsoluteFill style={{opacity: suave(u)}}>{entra}</AbsoluteFill>
      </>
    );
  if (tipo === 'zoom') {
    const flash = Math.max(0, 1 - Math.abs(u - 0.5) / 0.18);
    return (
      <>
        {u < 0.5 ? (
          <AbsoluteFill style={{scale: String(1 + 0.8 * suave(u / 0.5)), rotate: `${4 * suave(u / 0.5)}deg`}}>{sale}</AbsoluteFill>
        ) : (
          <AbsoluteFill style={{scale: String(1.8 - 0.8 * salida((u - 0.5) / 0.5)), rotate: `${-4 * (1 - salida((u - 0.5) / 0.5))}deg`}}>{entra}</AbsoluteFill>
        )}
        <AbsoluteFill style={{backgroundColor: '#fffbe8', opacity: 0.55 * flash}} />
      </>
    );
  }
  if (tipo === 'barrido') {
    const x = W * (1 - salida(u));
    return (
      <>
        <AbsoluteFill style={{translate: `${x - W}px 0px`}}>{sale}</AbsoluteFill>
        <AbsoluteFill style={{translate: `${x}px 0px`}}>{entra}</AbsoluteFill>
        <svg width={W} height={H} style={{position: 'absolute', inset: 0}}>
          <rect x={x - 30} y={0} width={30} height={H} fill="#ffd23f" />
          <rect x={x - 36} y={0} width={8} height={H} fill={C} />
          <rect x={x} y={0} width={6} height={H} fill={C} />
          {Array.from({length: 7}, (_, i) => (
            <rect key={i} x={x + 20 + ((i * 37) % 60)} y={150 + i * 260} width={120 + ((i * 53) % 80)} height={8} rx={4} fill="#fff" opacity={0.6 * (1 - u)} />
          ))}
        </svg>
      </>
    );
  }
  return <AbsoluteFill>{entra}</AbsoluteFill>;
};

export const AsiNacio: React.FC<{archivo: string}> = ({archivo}) => {
  const frame = useCurrentFrame();
  const [datos, setDatos] = useState<Datos | null>(null);
  const [handle] = useState(() => delayRender('cargando los datos del video'));
  useEffect(() => {
    cargar(archivo)
      .then((d) => {
        setDatos(d);
        continueRender(handle);
      })
      .catch((e) => {
        throw e;
      });
  }, [archivo, handle]);
  if (!datos) return null;
  const c = datos.cuadros[Math.min(frame, datos.cuadros.length - 1)];
  const capa = (cp: Capa) => <CapaSvg capa={cp} t={c.t} datos={datos} />;
  const imagen = c.b && c.tr ? <Transicion tipo={c.tr[0]} u={c.tr[1]} sale={capa(c.b)} entra={capa(c.a)} /> : <AbsoluteFill>{capa(c.a)}</AbsoluteFill>;
  const k = c.tono;
  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      <AbsoluteFill style={{filter: k > 0.001 ? `sepia(${0.92 * k}) brightness(${1 + 0.04 * k}) contrast(${1 - 0.06 * k})` : undefined}}>{imagen}</AbsoluteFill>
      {/* viñeta del primer plano (más fuerte en el pasado: "película vieja") */}
      <svg width={W} height={H} style={{position: 'absolute', inset: 0}}>
        <defs>
          <radialGradient id="vin" cx="0.5" cy="0.5" r="0.75">
            <stop offset="0.6" stopColor="#120c1e" stopOpacity="0" />
            <stop offset="1" stopColor="#120c1e" stopOpacity={0.28 + 0.25 * k} />
          </radialGradient>
        </defs>
        <rect width={W} height={H} fill="url(#vin)" />
      </svg>
      {c.sub ? <svg width={W} height={H} style={{position: 'absolute', inset: 0}} dangerouslySetInnerHTML={{__html: c.sub}} /> : null}
    </AbsoluteFill>
  );
};
