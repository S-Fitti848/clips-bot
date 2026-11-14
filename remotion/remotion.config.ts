import {Config} from '@remotion/cli/config';

// Cuadros en JPEG (más livianos que PNG para pasar a ffmpeg); el audio lo pega Python después.
Config.setVideoImageFormat('jpeg');
Config.setJpegQuality(92);
Config.setOverwriteOutput(true);
