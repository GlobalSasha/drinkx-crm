// Карта дистрибьюторов и конкурентов внутри CRM, с сайдбаром. Сама карта —
// готовый HTML из app/map-embed; у неё своя шапка, поэтому PageHeader нет.
// Высота: на мобильном сверху липкая шапка приложения (~49px).
export default function MapPage() {
  return (
    <iframe
      src="/map-embed"
      title="Карта дистрибьюторов и конкурентов"
      className="block w-full border-0 h-[calc(100dvh-49px)] md:h-dvh"
    />
  );
}
