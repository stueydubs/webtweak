import { Composition } from "remotion";
import { WebtweakDemo } from "./WebtweakDemo";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="WebtweakDemo"
      component={WebtweakDemo}
      durationInFrames={660}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
