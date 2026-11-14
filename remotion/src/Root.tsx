import React from 'react';
import {Composition} from 'remotion';
import {AsiNacio, cargar} from './Video';

// Un solo video, armado con los datos por cuadro de exportar.py (public/<archivo>). El largo y los fps
// salen de esos datos. El audio NO va acá: lo pega Python con ffmpeg (la misma mezcla del motor actual).
export const RemotionRoot: React.FC = () => (
  <Composition
    id="AsiNacio"
    component={AsiNacio}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={30}
    defaultProps={{archivo: 'datos.json'}}
    calculateMetadata={async ({props}) => {
      const d = await cargar(props.archivo);
      return {durationInFrames: d.cuadros.length, fps: d.fps};
    }}
  />
);
