"""
Bancos de frases, palabras, vocabulario y plantillas para el Modo Radio
de La Rockola del Carpincho.
Contiene el lore de humedal, modismos rioplatenses, frases horarias,
reacciones de cabina, filtros léxicos y plantillas sintácticas.
"""

from __future__ import annotations

import random
import re

# ---------------------------------------------------------------------------
# Locutores y prosodia
# ---------------------------------------------------------------------------

VOICE_TOMAS = "es-AR-TomasNeural"
VOICE_ELENA = "es-AR-ElenaNeural"
VOICE_MARIA = "es-CR-MariaNeural"
VOICE_VALENTINA = "es-UY-ValentinaNeural"
VOICES = [VOICE_TOMAS, VOICE_ELENA, VOICE_MARIA, VOICE_VALENTINA]

VOICE_NAMES: dict[str, str] = {
	VOICE_TOMAS: "Tomás",
	VOICE_ELENA: "Elena",
	VOICE_MARIA: "María",
	VOICE_VALENTINA: "Valentina",
}

# Prosodia fija por locutor (personajes con impronta propia para sonar naturales y no robóticos)
VOICE_PROSODY: dict[str, dict[str, str]] = {
	VOICE_TOMAS: {
		"rate": "-4%",
		"pitch": "-3Hz",
		"volume": "+0%",
	},
	VOICE_ELENA: {
		"rate": "-6%",
		"pitch": "-4Hz",
		"volume": "+0%",
	},
	VOICE_MARIA: {
		"rate": "+3%",
		"pitch": "+1Hz",
		"volume": "+0%",
	},
	VOICE_VALENTINA: {
		"rate": "+2%",
		"pitch": "+0Hz",
		"volume": "+0%",
	},
}

DEFAULT_TTS_TIMEOUT: float = 12.0
DEFAULT_TTS_RETRIES: int = 3
DEFAULT_BG_VOLUME: float = 0.1

DEFAULT_RADIO_ARTIST: str = "Carpincho Locutor 🎙️"
DEFAULT_RADIO_ALBUM: str = "La Rockola del Carpincho"
DEFAULT_RADIO_TITLE: str = "Locución radial"
DEFAULT_COHOST_NAME: str = "compadre"
DEFAULT_HOST_NAME: str = "Carpincho Locutor"
DEFAULT_COHOST_DISPLAY_NAME: str = "Carpincho Co-conductor"

# ---------------------------------------------------------------------------
# Fortunas del Carpincho y Avisos Publicitarios
# ---------------------------------------------------------------------------

CARPINCHO_FORTUNES: list[str] = [
	"Che, no te apurés; el agua siempre llega a la orilla.",
	"Posta: el secreto del éxito carpincho es mate caliente, buena música y cero drama.",
	"Un carpinchazo de tema te arregla cualquier lunes; comprobado científicamente.",
	"Tranqui en el agua; que las olas se las lleven los apurados.",
	"El carpincho no se apura: sabe que el agua siempre llega.",
	"Tomate un mate, bajá un cambio y disfrutá el temazo que viene.",
	"La vida es corta como pata de carpincho: no te hagas drama por pavadas.",
	"No cuentes los mates que te tomás, hacé que cada mate cuente.",
	"Si la vida te tira limones, fijate si conseguís hielo y fernet.",
	"Tranquilo como carpincho en Nordelta.",
	"El secreto de la felicidad: buena música, agua tibia y cero apuro.",
	"Hoy es un gran día para no hacer nada y hacerlo con mucho estilo.",
	"El que madruga encuentra todo cerrado.",
	"No dejes para mañana lo que puedas procrastinar hoy con buena música.",
	"El asado une lo que el lunes separa.",
	"Donde manda carpincho, no manda marinero.",
	"Más vale pájaro en mano... que pájaro volando sobre tu cabeza.",
	"Un tropezón no es caída, pero si nadie te vio, mejor todavía.",
	"El mate dulce no es pecado, pero bueno, sobre gustos no hay nada escrito.",
	"Ojo al piojo: las mejores cosas de la vida te despeinan.",
	"Algún día los carpinchos dominarán el mundo... pero hoy tienen fiaca.",
	"No bombardeen Barrio Norte, pongan cumbia y rocanrol.",
	"Si no hay amor que no haya nada, pero que al menos haya música en La Rockola.",
	"El tiempo no para, pero vos podés frenar un toque a escuchar este temita.",
	"Todo un palo, ya lo ves: la música te salva una y otra vez.",
	"Pronto recibirás una visita inesperada... ojalá traiga facturas.",
	"Tu creatividad te llevará lejos, pero acordate de cargar la SUBE.",
	"Un gran viaje comienza con un solo paso... y una buena playlist.",
	"Sonreí: confundís a tus enemigos y le ponés onda a la tarde.",
	"El oráculo predice que la próxima canción te va a encantar.",
	"Más vale carpincho en laguna que cien mosquitos en la nuca.",
	"El que se va a Sevilla pierde su silla, pero el que se queda baila.",
	"Para el carpincho sabio, cada charco es un jacuzzi.",
	"A caballo regalado no se le miran los dientes, pero a la playlist sí.",
	"No hay mal que dure cien años, ni pena que una cumbia no cure.",
	"Ojo al piojo con los que te dicen que no pongas otro tema.",
	"Si el río suena, es porque un carpincho se tiró de bomba.",
	"Billetera mata galán, pero temazo mata billetera.",
	"El oráculo dice: relajá la mandíbula y metele play.",
	"No te preocupes por el qué dirán: el carpincho toma sol y le importa un comino.",
	"El que busca encuentra... menos las llaves cuando estás apurado.",
	"Mejor solo que mal acompañado, pero con buena música nunca estás solo.",
	"Cuidado con el que te dice que no toma fernet... algo oculta.",
	"La música limpia el alma del polvo de la rutina diaria.",
	"El mate amargo y la música al palo, como manda la ley criolla.",
	"Todo concluye al fin, todo termina... menos esta fiesta en La Rockola.",
	"No llores porque terminó, ponete otro temazo y sonreí.",
	"El oráculo avisa: se viene un temazo de aquellos, prepará el mate.",
	"A seguro se lo llevaron preso, pero al carpincho lo dejaron en el agua.",
	"Lo bueno si breve, dos veces bueno... excepto cuando suena un temazo.",
	"No empujen que hay música y mates para todos.",
	"El que ríe último... probablemente no entendió el chiste.",
	"Las penas se van cantando, o por lo menos se disimulan bastante bien.",
	"El carpincho zen dice: respirá hondo y dejate llevar por el ritmo.",
	"Si la tarde viene pesada, una buena cumbia te la acomoda.",
	"No hay camino a la felicidad: la felicidad es escuchar música entre amigos.",
	"Menos drama y más cumbia, esa es la receta del éxito.",
	"Un sabio dijo una vez... ¡subile el volumen que este tema me encanta!",
	"El oráculo predice: tu día va a mejorar en un cien por ciento con este tema.",
	# Filosofía zen de pantano
	"El carpincho no compite con la corriente: flota con dignidad y que el río haga el esfuerzo.",
	"Conflicto territorial lo tienen los que construyen sobre el humedal; nosotros ya estábamos acá.",
	"Dormir doce horas sobre el lodo no es pereza: es comunión con la madre tierra.",
	"Si un problema no se resuelve tomando un mate al sol, entonces no tiene solución.",
	"Hacete amigo del yacaré: no para abrazarlo, sino para saber bien por dónde nada.",
	"La paz mental es ver pasar la lancha a motor y ni siquiera parpadear.",
	"No le pidas peras al olmo ni velocidad a un roedor de setenta kilos.",
	# Cotidianeidad de humedal, dilemas criollos y refranero refactorizado
	"El que no nada se ahoga, y el que no chupa el mate a tiempo se le enfría la pava.",
	"A seguro se lo llevó la correntada del Paraná, pero al carpincho lo salvó la paciencia.",
	"En casa de herrero, cuchillo de tacuara y la bombilla tapada con yerba barbacuá.",
	"La vida es como remar contra la corriente: si no le metés ritmo, terminás en el juncal de enfrente.",
	"El verdadero dilema nacional no es la grieta: es si el vacío a la estaca se come a punto o jugoso.",
	"No te pelees por quién lavó la bombilla: poné pava nueva y cebate otro con espuma.",
	"Hacer la cola en la orilla para esperar la lancha colectiva enseña más templanza que diez años de yoga.",
	"Con el precio del kilo de yerba por las nubes, al mate se lo estira hasta que parezca sopa de pasto.",
	"La pizza de molde sostiene el alma, pero la de piedra te apura las ganas de seguir bailando.",
	"Mucho hielo en el fernet es de cobarde, pero sin hielo es una locura de verano.",
	"El carpincho no le teme a la sudestada: acomoda las ramas y se echa un sueñito reparador.",
	"Si la lancha te llena de olas el rancho, no te enojes: disfrutá el vaivén y metele otro amargo.",
	"Más vale mate lavado en mano que diez termos importados vacíos.",
	"El que madruga en la isla ve salir el sol, pero el que duerme la siesta llega entero al fogón.",
	"No hay trámite en la orilla que un buen chamamé de fondo no te haga más llevadero.",
	"En la mesa del asado no se discute de política: se discute quién se quedó con el último pedazo de tira.",
	"El secreto de la paz interior: cara de nada, lomo al sol y que el barro tape las malas ondas.",
	"Gato escaldado del agua huye, pero carpincho curtido se tira de panza con cualquier marea.",
	"El mundo gira muy rápido para los que andan a los piques; en el arroyo todo tiene su compás.",
	"El oráculo de la laguna sentencia: si la yerba todavía tiene palo, ese mate aguanta tres vueltas más.",
	# Saludos y mensajes de los oyentes
	"Un saludo enorme para Horacio de las islas, que nos escucha mientras le tira un pedazo de pan a los carpinchos del fondo. ¡Grande, Horacio!",
	"Línea abierta en la Rockola. Saludo especial para toda la gente que nos saca a pasear en el estéreo del auto, del camión, o de la motito de delivery.",
	'Mensajito que entra al WhatsApp: "Locutor, acá los pibes del taller de chapa y pintura pidiendo cumbia para que el soplete agarre ritmo". ¡Abrazo a esa barra laburadora!',
	'Nos escribe Gladys desde Berazategui: "Cebando unos amargos con cascarita de naranja mientras escucho La Rockola". ¡Esa es la actitud, Gladys!',
	'Atenti este mensaje: "Mandale un saludo al Beto que prometió prender el fuego a las doce y todavía está buscando el carbón". ¡Apurate, Beto, que la hinchada tiene hambre!',
	'Entra un audio de oyente: "Acá el chofer de la línea sesenta clavado en el puente pero con la radio al palo. Hacen el viaje un lujo". ¡Fuerza en ese volante, maestro!',
	'Mensaje de la comunidad: "Un saludo para los muchachos de la obra que están festejando el final de la losa con unos sánguches de salame y queso". ¡Salud, laburantes!',
	'Nos mandan foto al WhatsApp: "Mirá cómo duerme la siesta el perro con La Rockola de fondo". Ronca acompasado con el bajo, ¡un fenómeno!',
	'Llega un mensaje desde la ruta: "Acá el camionero Jorge pasando por Zárate con la cabina llena de mates y temazos". ¡Buenas rutas y buen viaje, Jorge!',
	'Audio de oyente al dial: "Locutor, decile a mi compañero de oficina que deje de robarme las criollitas". ¡Quedaste escrachado al aire, compadre!',
	'Nos escribe Pocho desde la isla: "Acá desenredando la red con la radio a batería colgada de un sauce". ¡Buena pesca y abrazo grande, Pocho!',
	'Mensaje de los que madrugan: "Acá la guardia del hospital metiéndole onda a la madrugada con La Rockola". ¡Un aplauso de pie para todo el equipo de salud!',
	'Otro mensaje que llega al control: "Saludo para la tía Marta que cumple ochenta y está bailando en chancletas en el patio". ¡Qué grande la tía Marta, esa vitalidad vale oro!',
	'WhatsApp de la radio: "Acá esperando que abra la panadería para comprar las criollitas calientes". ¡El que madruga Dios lo ayuda, pero el panadero más!',
	# Filosofía de Carpincho (Humor absurdo)
	"Señoras y señores, recuerden el consejo del día: la vida es como un carpincho tomando sol al costado del río... hay que tomársela con calma y que nada te altere.",
	"¿Problemas de dinero? ¿Problemas de amor? Olvidadlo por tres minutos y medio. Dejate llevar por el ritmo de la Rockola del Carpincho.",
	"Me preguntan por privado de qué especie es el Carpincho de la Rockola. Es de la especie que sabe disfrutar de la buena música, chamigo.",
	# "Gisella, ya salió el Gerardo el Magias 3, con Gerardo de Revilla y su caballo maravilloso. ¡No te lo pierdas!",
]

CARPINCHO_ADS: list[str] = [
	"Espacio publicitario: Yerba Mate El Carpincho Mimoso, estacionada dos años en laguna natural. Un mate que te acaricia el alma.",
	"Publicidad: Pastos y Juncos Don Pedro. Los mejores brotes tiernos del Delta para rumiar en la orilla mientras suena La Rockola.",
	"Aviso inmobiliario: Inmobiliaria El Bañado. Venta de lotes con costa propia y vista panorámica a Nordelta. Cero expensas, pura paz.",
	"Publicidad: Protector solar Piel de Carpincho, factor ochenta. Tomate un solazo en la barranca sin quemarte el cuero.",
	"Espacio publicitario: Ponchos y Boinas El Yacaré. Elegancia criolla para las noches frescas en el pajonal.",
	"Aviso comercial: Remises La Nutria. Te cruzamos el río a nado o en canoa. Más rápidos que doradillo en bajante.",
	"Espacio publicitario: Fernet Laguna Negra con dos hielos y coca. El combustible oficial de los carpinchos trasnochadores.",
	"Publicidad: Spa Termal Los Esteros. Baños de fango curativo y masajes con caña tacuara. Salís como nuevo, hecho una seda.",
	"Aviso comercial: Seguros La Madriguera. Si la crecida te llega al cogote, nosotros te cubrimos la cueva. Dormí sin frazada.",
	"Publicidad: Ferretería Don Roedor. Bombas de achique, alambrados olímpicos y machetes para desmalezar la isla.",
	"Espacio publicitario: Barbería y Peluquería Bigote Criollo. Corte degrade, recorte de bigotes y peinado a contrapelo para deslumbrar en la laguna.",
	"Aviso parroquial: Academia Los Carpincheros. Clases de natación sincronizada y flotación tipo tronco para principiantes.",
	"Publicidad: Astilleros La Balsa. Botes a remo, kayaks de madera y balsas de totora con garantía de por vida.",
	"Espacio publicitario: Café de Algarroba y Facturas Don Ceibo. El desayuno ideal antes de tirarse a la sombra a hacer la siesta.",
	"Publicidad: Colchones Sommier Paja Brava. Firmeza garantizada para dormir doce horas seguidas como un señor carpincho.",
	"Aviso comercial: Cervecería Artesanal El Pantano. Con lúpulo silvestre y agua fresca de vertiente isleña. Pedite una pinta bien helada.",
	"Espacio publicitario: Sombreros de Paja Don Bigote. Frescura, sombra y porte gaucho para caminar por el terraplén.",
	"Aviso parroquial: Repelente Chau Mosquito. Para que no te piquen las orejas mientras disfrutás de un buen chamamé.",
	"Publicidad: Panadería La Espiga Verde. Medialunas de grasa calentitas a toda hora para acompañar los amargos.",
	"Espacio publicitario: Neumáticos La Huella. Cámaras inflables para flotar panza arriba toda la tarde en el arroyo.",
	"Publicidad: Remises La Corvina. Cruzamos el arroyo sin salpicarte la boina. Puntualidad isleña garantizada.",
	"Aviso parroquial: Se extravió una calabaza de mate curada con yerba misionera por la zona de los sauces. Recompensa en tortas fritas.",
	"Espacio publicitario: Colchones de Totora El Descanso. Si te despertás contracturado, te devolvemos dos atados de juncos.",
	"Aviso comercial: Pizzería El Camalote. Muzzarella elástica y masa a la piedra cocinada con leña de espinillo. Envío en canoa a todo el brazo del río.",
	"Publicidad: Alarma La Nutria. Avisamos cuando sube la marea a los gritos limpios. Sin cables ni internet.",
	"Publicidad: Plomería El Remanso. Destape de madrigueras inundadas y desagües de bañados con caña tacuara. Presupuestos sin cargo en la bajada del puente.",
	"Espacio publicitario: Escuela de Canotaje La Nutria Feliz. Clases de remo y timonel para principiantes. Aprendé a no chocar los troncos con estilo.",
	"Aviso parroquial: Trueque del Delta. Cambio dos bolsas de pasto tierno recién cortado por un vinilo de cumbia santafesina en buen estado. Tratar en el muelle tres.",
	"Publicidad: Fletes Fluviales Don Bigote. Mudanzas de rancho, traslado de fardos de totora y transporte de leña seca. Si flota, te lo llevamos.",
	"Espacio publicitario: Guardería de Camalotes El Espinillo. Dejá flotando tus plantas acuáticas en un ambiente seguro mientras te vas de viaje.",
	"Aviso comercial: Venta de Bombillas Autolimpiantes La Criolla. No se tapan ni con la yerba más polvorienta del almacén isleño.",
	"Publicidad: Herrería Ribereña El Sauce. Parrillas flotantes, asadores a la estaca inoxidables y ganchos para amarrar la canoa sin perder el sueño.",
	"Espacio publicitario: Cooperativa La Totora. Teñido artesanal de juncos y esterillas para que tu cueva parezca una postal de revista.",
	"Aviso parroquial: Atención vecinos del arroyo: se extravió un termo de acero inoxidable con calcomanías de cumbia. Si lo ven flotando, avisen a la radio.",
	"Publicidad: Zapatería El Carpincho Andariego. Botas de goma reforzadas para caminar el fango sin dejar la chancleta pegada en el fondo.",
	"Espacio publicitario: Panadería y Confitería El Hornero. Pastelitos de membrillo con masa hojaldrada y cañoncitos de dulce de leche para el mate de la tarde.",
	"Aviso comercial: Astillero Los Tres Bagres. Calafateado de botes a remo y reparación de quillas con brea natural del monte.",
	"Publicidad: Fumigaciones La Garza. Control ecológico de tábanos y jejenes con sapos adiestrados. Eficacia comprobada en todo el humedal.",
	"Espacio publicitario: Almacén de Ramos Generales La Bajada. Harina, grasa de pella, yerba por bolsa y alpargatas de todos los números.",
	"Aviso parroquial: Taller de Payadas y Guitarreadas Don Ceferino. Clases abiertas los sábados bajo el sauce llorón. Traer instrumento y mate propio.",
]

# ---------------------------------------------------------------------------
# Bancos de frases culturales y radiofonía popular
# ---------------------------------------------------------------------------

TRANSITO_FLUVIAL_Y_CAMINOS: list[str] = [
	"Alerta de tránsito fluvial: balsa maroma varada a la altura del arroyo Las Víboras por bajante repentina. Tengan paciencia y preparen otra pava de mate.",
	"La lancha colectiva de las ocho viene con cuarenta minutos de demora porque enganchó un colchón de camalotes en la hélice.",
	"Atención baqueanos: sudestada brava tapando los pilotes del puente viejo. Se recomienda cruzar despacito o esperar a que baje la marea.",
	"Tránsito en el humedal: corte total en la bajada del terraplén por barro greda. Ni con doble tracción pasan, así que no hagan macanas.",
	"Camino de ripio hacia el puerto totalmente anegado por el desborde del zanjón. Vayan al trote lento y con las luces prendidas.",
	"Aviso a los navegantes del Delta: banco de arena nuevo frente a la isla del Francés. Si van a fondo van a terminar plantados en el barro.",
	"La balsa de paso Don Romualdo opera con servicio reducido hasta que desenreden las ramas de sauce de la timonera.",
	"Corte parcial en el camino vecinal del bajo: una familia de doce carpinchos se echó a tomar sol cruzando la calzada y nadie se anima a apurarlos.",
	"Tránsito pesado en la curva del ceibo: huellas de tractor de medio metro llenas de agua. El que no tenga botas de caña alta que pegue la vuelta.",
	"Demoras en el embarcadero municipal: el muelle flotante quedó inclinado por la crecida y están desembarcando de a uno por vez.",
	"Reporte de caminos: la ruta provincial tiene tres lagunas bravas entre el puente de hierro y la estancia. Pasen en primera y con envión.",
	"Aviso fluvial: remolcador empujando barcazas a paso de hombre en el canal principal. Cuidado con el oleaje que les va a sacudir la canoa.",
	"Camino isleño intransitable: el camión lechero quedó encajado hasta los ejes en el zanjón norte. Se solicita ayuda con cadenas y buena voluntad.",
	"Precaución en la desembocadura: sudestada empujando un islote entero de totoras a la deriva con dos nutrias arriba mirando el paisaje.",
	"Balsa comunal fuera de servicio hasta nuevo aviso: el baqueano está cambiando la grasa del malacate con una espátula de cocina.",
	"Paso a nivel del viejo ramal cortado: el agua de lluvia superó la altura de los durmientes. Desvíen por la huella de tierra seca.",
	"Lancha almacenera demorada en el muelle de madera: se armó ronda de charla con las vecinas y todavía no descargaron las bolsas de harina.",
	"Aviso de ruta ribereña: calzada resbaladiza por barro negro en la bajada del puente amarillo. Tiren rebajes suaves y no claven los frenos.",
	"Alerta para boteros y canoeros: viento sur en popa levantando olitas cortas en el canal de acceso. Remen parejo y ajusten el salvavidas.",
	"Estado de caminos del norte: huella cortada en la cañada por desborde del arroyo. El que quiera cruzar que pida permiso al puestero o nade con poncho.",
]

AVISOS_PARROQUIALES_Y_EXTRAVIOS: list[str] = [
	"Aviso parroquial: se busca termo de acero abollado en la base con calcomanías de Los Palmeras. Se cayó de la canoa cerca del juncal.",
	"Solidaridad comunitaria: al compadre Cacho se le escapó un chivo overo que responde al nombre de Pichicho. Fue visto rumiando cerca de la capilla.",
	"Objeto perdido en la costa: apareció una reposera de caño a rayas verdes y blancas olvidada en el banco de arena. El dueño que la reclame con mate de por medio.",
	"Urgente del pueblo: se busca garrafa de diez kilos pintada de azul con manija soldada. Desapareció misteriosamente del patio durante el asado del domingo.",
	"Extravío insólito: don Evaristo perdió una boina de paño negro de tres estaciones entre el almacén y el muelle tres. Recompensa dos docenas de empanadas.",
	"Aviso de la parroquia: apareció flotando un remo de madera de sauce tallado a mano con iniciales borrosas. Se guarda en la sacristía hasta que aparezca el botero.",
	"Comunidad alerta: se extravió un carpincho domesticado con cinta roja en el cuello. No muerde, pero si le convidan torta frita no se va nunca más.",
	"Pérdida en el balneario: vecina busca desesperadamente par de chancletas de goma talle cuarenta y dos perdidas en la resaca del río.",
	"Aviso parroquial: se ofrece permuta de una pava enlozada con el pico medio torcido por una bombilla alpaca que no caliente los labios.",
	"Atención vecinos: encontraron un cajón de herramientas de chapa oxidada al costado del terraplén. Adentro tiene tres llaves fijas y un paquete de yerba.",
	"Solidaridad isleña: se busca cuchillo criollo con cabo de guampa de ciervo extraviado en la última carneada familiar. Se ofrece gratificación generosa.",
	"Pérdida comunitaria: don Zoilo olvidó su radio a pilas sintonizada en La Rockola sobre el capó de la chata. Pide que por favor no le cambien el dial.",
	"Aviso de la capilla: el domingo después de misa habrá rifa parroquial de un lechón y dos costillares a beneficio del techo del salón comunal.",
	"Extravío en el bañado: se busca perro barcino de orejas caídas que salió corriendo atrás de una nutria y no volvió para la hora de comer.",
	"Objeto hallado: se rescató de la correntada un fuentón de plástico amarillo con tres mudas de ropa mojada. Reclamar en el destacamento de prefectura.",
	"Aviso parroquial: don Cosme busca su sombrero de paja de ala ancha que se le voló con el viento mientras cruzaba el arroyo en bote.",
	"Mensaje vecinal: se extraviaron tres gallinas brizadas del corral de doña Rosa. Avisan que si las ven cerca de una olla avisen urgente.",
	"Pérdidas insólitas: apareció una parrilla plegable de dos pisos olvidada debajo del ceibo grande. Tiene restos de grasa fresca de buen vacío.",
	"Solidaridad del pago: se busca carretilla de madera con rueda de hierro prestada en la primavera pasada y nunca devuelta al galpón de la esquina.",
	"Aviso de utilidad pública: se perdió una conservadora de telgopor blanca con hielo y seis botellas de cerveza. Hay desesperación en el taller mecánico.",
]

ALERTAS_INCOMODIDAD_CRIOLLA: list[str] = [
	"Alerta de incomodidad criolla: humedad del cien por ciento en el humedal. Las puertas de madera se hincharon tanto que para salir del rancho hay que pedir permiso.",
	"Reporte meteorológico satírico: nube espesa de mosquitos sobrevolando la costa. No piquen repelente en aerosol porque los bichos se lo toman como aperitivo.",
	"Atención Norte argentino: calor infernal de siesta tucumana donde el asfalto parece goma fresca y hasta las palomas buscan sombra abajo de los autos.",
	"Alerta por viento Zonda en la precordillera: sopla aire caliente como puerta de horno de panadería abierta. Bajen las persianas y tomen agua fresca.",
	"Sensación térmica en la laguna: pesadez ribereña absoluta. El mate amargo está sudando en la pava antes de tocar la bombilla.",
	"Aviso de plaga criolla: invasión de jejenes en el bañado. Son chiquitos pero tienen la mala leche concentrada de un yacaré con dolor de muelas.",
	"Reporte del clima pesadito: la sal del salero se convirtió en una piedra sólida por la humedad. Se recomienda picarla con destornillador.",
	"Alerta tucumana: ¡ura qué calor que hace chango! A las dos de la tarde el sol pega tan fuerte que el perro duerme adentro de la heladera desconectada.",
	"Viento Norte rabioso azotando la cuenca: tierra colorada volando por todos lados y la ropa recién colgada secándose en cuatro minutos reloj.",
	"Incomodidad climática total: los tábanos andan con chaleco antibalas y no les hace mella ni el manotazo más certero de gaucho enojado.",
	"Reporte del cielo isleño: calor pesado con olor a barro tibio. La única actividad física recomendada es flotar como corcho en la sombra del sauce.",
	"Alerta de siesta criolla: prohibido hacer ruido con la motoguadaña entre la una y las cinco. La condena social del pueblo puede ser implacable.",
	"Termómetro carpincho al rojo vivo: cuarenta grados a la sombra y el ventilador de pie tira menos aire que un suspiro de abuela.",
	"Humedad de pantano nivel crítico: las sábanas se sienten mojadas antes de acostarse y el pan francés parece una esponja de cocina.",
	"Aviso criollo por Zonda caliente: el aire quema las pestañas y las hojas secas bailan en remolino sobre el patio de tierra. Calma chicha adentro.",
	"Mosquitos tamaño helicóptero patrullando el muelle: si se descuidan dos minutos les levantan la reposera en el aire con ustedes sentados.",
	"Calorazo santiagueño y tucumano de antología: el pavimento amaga con tragarse las ruedas de la bicicleta. Ni el gato se anima a cruzar la vereda.",
	"Reporte de pesadez ambiental: la masa de las tortas fritas leudó sola en la mesada sin necesidad de prender el fuego del horno.",
	"Alerta de jejenes en la barranca: atacan los tobillos con saña milimétrica. La mezcla de barro con ceniza es la única armadura que funciona.",
	"Clima pesado de tormenta que amaga y no revienta: el cielo está negro como sobaco de cuervo y la modorra carpincha es ley nacional.",
]

SEPARADORES_Y_SLOGANS: list[str] = [
	"Estás en La Rockola, noventa y ocho punto siete en modulación carpincha. La radio que no te abandona en la orilla.",
	"Donde manda carpincho, el dial no cambia. Sintonizás la sintonía chamamecera y cumbiera del Delta.",
	"La Rockola del Carpincho: transmitiendo con antena de tacuara y corazón de sauce para toda la cuenca.",
	"Música de la buena, mate espumoso y cero drama. Estás prendido a La Rockola.",
	"Noventa y ocho punto siete MHz: la frecuencia más fresca del humedal. Ponete cómodo que sobra música.",
	"La Rockola: doscientos caballos de potencia musical para empujar cualquier bajante.",
	"Ni FM comercial ni playlist enlatada: esto es La Rockola del Carpincho, radio hecha por y para los amigos.",
	"Subile dos rayitas al parlante que acá no cobramos entrada. Suena La Rockola.",
	"Desde la orilla del río para el mundo entero: La Rockola del Carpincho, tu cable a tierra musical.",
	"En la isla, en la ruta o en el taller: la banda de La Rockola te hace la segunda todo el día.",
	"La Rockola del Carpincho: la única radio con aroma a leña de espinillo y mate recién cebado.",
	"Sintonizás La Rockola: pegale un trago al tereré y dejate llevar por el ritmo ribereño.",
	"Cabina de transmisión flotante en el arroyo: acá no hay apuro, acá hay música de verdad.",
	"La Rockola: noventa y ocho punto siete en el dial, cien por ciento carpincha en el corazón.",
	"Frecuencia libre de malas ondas y repleta de temazos. Estás en La Rockola.",
	"Hacete amigo del ritmo y descansá la mente: transmite La Rockola del Carpincho.",
	"La Rockola: la emisora que te ceba el mate justo cuando más lo necesitás.",
	"Sonido criollo de alta fidelidad ribereña. Conectate a La Rockola del Carpincho.",
	"Donde la cumbia santafesina y el chamamé se dan la mano: La Rockola en el aire.",
	"Transmite La Rockola del Carpincho: tu compañía fiel cuando el sol cae sobre la laguna.",
]

DEDICATORIAS_OYENTES: list[str] = [
	'Mensaje al WhatsApp de la radio: "Acá los muchachos del taller mecánico El Pistón pidiendo una cumbia de Leo Mattioli para enderezar el chasis de una F-100". ¡Va con dedicatoria!',
	'Entra mensaje desde la terapia: "La guardia médica del hospital de San Pedro pide un cuartetazo cordobés de La Mona para levantar la noche larga". ¡Fuerza a ese equipo de salud!',
	'Audio de camionero en la ruta doce: "Metale un chamamé de Mario Bofill compadre, que vengo cargado de naranjas y con el mate recién armado". ¡Buen viaje por el Litoral!',
	'Nos escriben desde la canoa: "Acá los pescadores del arroyo La Paloma esperando el pique con La Rockola de fondo. Tiren un temazo de Los Palmeras que la boga no sale con silencio".',
	'WhatsApp del dial: "Mandale un saludo a los pibes de la gomería que están emparchando la rueda de un tractor con una cumbia de Karicia de fondo". ¡Puro pulmón muchachos!',
	'Llega mensaje desde Tucumán: "Chango, poné un folclore bien sachero de Raly Barrionuevo que estamos amasando empanadas en el patio con cuarenta grados". ¡Qué manjar compadre!',
	'Mensaje de la obra en construcción: "Locutor querido, tirate un rocanrol de Los Redondos para los albañiles que estamos terminando el revoque fino bajo el solazo". ¡Salud laburantes!',
	'Audio de puestero de campo: "Acá escuchando desde el galpón de esquila; largate una zamba de Cafrune para acompañar el amargo de la tarde". ¡Abrazo paisano!',
	'Nos escribe la barra del asado: "Decile al parrillero que afloje con el fernet y dé vuelta el vacío antes de que se haga carbón. Ponete algo de Rodrigo para bailar".',
	'Mensaje de la lancha colectiva: "El capitán del muelle cuatro pide chamamé con acordeón verdulera para alegrar a los pasajeros que vienen cansados del laburo".',
	'WhatsApp de los metalúrgicos: "Acá en la tornería con el ruido de las máquinas al palo pero La Rockola al doble de volumen. Queremos cumbia santafesina clásica".',
	'Llega audio desde Corrientes: "Che locutor, mandale un abrazo a mi compadre Néstor que se quedó dormido en la canoa y la marea se lo está llevando despacito al juncal".',
	'Mensajito de panadería de pueblo: "Amasando las medialunas de grasa desde las cuatro de la mañana con La Rockola bien prendida. Pedimos cuarteto del bueno para no cabecear".',
	'Audio de recolectores de basura: "Un saludo grande para la cuadrilla de la noche que limpia el pueblo escuchando rock nacional en el camión. ¡Aguante La Rockola!".',
	'Llega mensaje de la estación de servicio: "Los chicos del turno noche del surtidor pedimos cumbia con acordeón para que no nos gane la modorra de las tres de la mañana".',
	'WhatsApp del frigorífico: "Acá en el muelle de carga con los compañeros pidiendo un chamamé de Montiel bien sentido para recordar los pagos entrerrianos".',
	'Mensaje de almacén isleño: "La patrona está pesando los fideos y pide una chacarera de Los Manseros para alegrar el mostrador. ¡Abrazo para toda la audiencia!".',
	'Audio de chofer de colectivo de larga distancia: "Cruzando el puente Zárate Brazo Largo con el pasaje durmiendo y el mate caliente. Tirate un tema de Spinetta para el chofer".',
	'WhatsApp de taller de chapa: "Acá lijando masilla fina en una puerta picada. Que suene Gilda bien fuerte que con alegría el trabajo sale más rápido y derechito".',
	'Nos escriben los guardavidas del arroyo: "Mirando el agua y cuidando a los bañistas con La Rockola en la caseta. Un saludo para todos los carpinchos que nadan tranquilos".',
]

CARPINCHO_ADS.extend(AVISOS_PARROQUIALES_Y_EXTRAVIOS)
CARPINCHO_ADS.extend(TRANSITO_FLUVIAL_Y_CAMINOS)
CARPINCHO_FORTUNES.extend(ALERTAS_INCOMODIDAD_CRIOLLA)
CARPINCHO_FORTUNES.extend(DEDICATORIAS_OYENTES)

CARPINCHO_FORTUNES.extend(CARPINCHO_ADS)

# ---------------------------------------------------------------------------
# Frases de apertura, intro, lead-in y cierre radial
# ---------------------------------------------------------------------------

RADIO_INTROS: list[str] = [
	"Micrófono abierto, patas en el agua. Así arranca La Rockola.",
	"¿Quién dejó la pava en el control central? Bueno, no importa... ¡al aire en La Rockola!",
	"Directo desde el juncal para toda la cuenca: transmite La Rockola del Carpincho.",
	"Sintonizando la única frecuencia que no se hunde ni con la sudestada.",
	"Acomodate en el barro, fiera. Estás escuchando La Rockola del Carpincho.",
	"Secándonos al solcito de la orilla y metiendo buena música.",
	"En el aire de La Rockola del Carpincho.",
	"¡Buenas gente linda de La Rockola!",
	"La hora en La Rockola.",
	"Sintonizando La Rockola del Carpincho.",
	"¡Seguimos haciendo el aguante en La Rockola!",
	"Un matecito en La Rockola y seguimos.",
	"Transmite La Rockola del Carpincho.",
	"Che, buenas y santas gente linda; acá estamos en La Rockola del Carpincho.",
	"Posta, qué lindo estar acá en La Rockola; sintonizando buena onda.",
	"¡Al pelo la música en La Rockola del Carpincho!",
	"Tranqui en el agua, mate en mano... transmite La Rockola del Carpincho.",
	"Aire en el Delta, brisa en la cara y la pava silbando en la consola. ¡Arranca La Rockola!",
	"Con el agua a media pata y el mate recién espumado, abrimos los micrófonos en La Rockola.",
	"Se escucha el rumor del río de fondo y el mejor ritmo en el dial. ¡Bienvenidos a La Rockola del Carpincho!",
	"La marea sube pero la música sube todavía más. Sintonizás La Rockola desde la orilla.",
	"Dejamos la canoa bien amarrada al sauce y nos metemos al estudio. ¡En el aire La Rockola!",
	"Despertando a los bagres del fondo con buen volumen. ¡Transmite La Rockola del Carpincho!",
	"Olorcito a sauce mojado, mates amargos y la mejor compañía en el aire de La Rockola.",
	"Desde la cabina de madera sobre pilotes, tiramos buena vibra a todo el humedal. ¡Esto es La Rockola!",
	"Corré el camalote de la antena que salimos al aire con todo en La Rockola del Carpincho.",
	"Tardecita dorada en la ribera y nosotros listos para hacerte el aguante en La Rockola.",
	# El arranque y la energía de la mañana
	"¡Sintonía total en todo el país! Estás en la Rockola del Carpincho, donde la música no para y los carpinchos tampoco. ¡Buen día para todos!",
	"¡Arriba, arriba, arriba! Subí el volumen que si el vecino se queja, lo invitamos a tomar unos mates. ¡Arrancamos otra hora de puros éxitos!",
	"Estás escuchando la Rockola del Carpincho. Conduce quien les habla, musicaliza el destino, y del otro lado... ¡la mejor audiencia del planeta!",
	"¡Hola, hola! Reportándonos en vivo desde el mejor rincón del dial. Si estás yendo a laburar, paciencia; si estás volviendo, ¡sos un héroe nacional!",
	# Cierre de tanda / Separadores cortos
	"La Rockola del Carpincho: tu dosis diaria de música, mates y buena onda. No aceptes imitaciones.",
]
RADIO_INTROS.extend(SEPARADORES_Y_SLOGANS)

LEAD_INS_FORTUNA: list[str] = [
	"Momento de rumiar una idea mientras chupás la bombilla...",
	"Pará la oreja que esto no te lo enseñan en la escuela de natación.",
	"Un consejo milenario directo del barro profundo.",
	"Momento de la galletita de la fortuna...",
	"Ojo al piojo con lo que dice el oráculo de La Rockola.",
	"Sabiduría carpinchera para el alma.",
	"Tiramos una frase para reflexionar mientras te tomás unos mates.",
	"Dice la fortuna del día...",
	"Atenti a esta reflexión carpinchera.",
	"Che, atenti al oráculo; sabiduría pura de la laguna.",
	"Posta, escuchate esta reflexión carpinchera.",
	"Pará la oreja; mirá lo que nos deja el oráculo hoy.",
	"Pará un segundo el remo que bajó línea el oráculo del pajonal.",
	"Atenti a la orilla, que el carpincho sabio nos dejó este mensaje.",
	"Dejá la pava en la mesa y abrí bien las orejas con esta reflexión.",
	"Mirá la frase que nos mandaron desde el fondo de los esteros.",
	"Anotate esta máxima isleña antes de cebar el próximo amargo.",
	"El oráculo de la ribera tiene un consejo que te va a volar la boina.",
	"Frená un cambio y escuchá lo que enseña la calma de la laguna.",
	"Palabra santa que llega navegando entre los camalotes.",
	"Abrí la mente y sentí la posta que nos trae la corriente.",
	"Para vos que andás medio a las corridas, prestale atención a esta joyita.",
]

LEAD_INS_AVISOS: list[str] = [
	"Espacio publicitario en La Rockola.",
	"Atenti a este aviso de la comunidad carpinchera.",
	"Mensaje de nuestros queridos auspiciantes.",
	"Aviso importante de la vecindad de los bañados.",
	"Atendé lo que nos bajó la capitanía de la laguna.",
	"Llegó un aviso urgente a la mesa de control; pará la oreja:",
	"Parte comunitario y comercial en el aire de La Rockola:",
	"Avisos parroquiales y novedades de la cuenca; tomá nota:",
	"Llegó un mensaje en botella al terraplén; escuchá...",
]

LEAD_INS_OYENTES: list[str] = [
	"Suena la campanita de mensajes en cabina; escuchate este:",
	"Bandeja de mensajes hasta las manos en La Rockola; atendé:",
	"Llegó un audio de WhatsApp a la consola; mirá lo que piden:",
	"Mensaje de la muchachada que nos acompaña del otro lado:",
	"Pará la oreja que los oyentes mandan reporte en vivo:",
	"Revisando los mensajes del pueblo en La Rockola; escuchá:",
	"La audiencia se hace sentir en el WhatsApp de la radio; atendé:",
]

LEAD_INS_ALERTAS: list[str] = [
	"Alerta especial de incomodidad criolla en el dial:",
	"Reporte urgente desde la costa; ojo al piojo:",
	"Atención navegantes y vecinos del humedal con este parte:",
	"Aviso meteorológico no oficial de los bañados:",
	"Pará la oreja que se picó el ambiente en la ribera:",
]

LEAD_INS_BY_CATEGORY: dict[str, list[str]] = {
	"fortuna": LEAD_INS_FORTUNA,
	"aviso": LEAD_INS_AVISOS,
	"oyentes": LEAD_INS_OYENTES,
	"alerta_criolla": LEAD_INS_ALERTAS,
}

RADIO_LEAD_INS: list[str] = LEAD_INS_FORTUNA + LEAD_INS_AVISOS + LEAD_INS_OYENTES + LEAD_INS_ALERTAS

RADIO_OUTROS: list[str] = [
	"Dejamos de parlotear y que hable el bajo. ¡Metele play!",
	"Acomodá el lomo en la orilla que este tema arranca al palo.",
	"Menos charla y más cumbia. ¡Pegale!",
	"¡Subile al parlante antes de que nos tape la marea!",
	"Se viene un clásico de aquellos... ¡hacete un espacio y bailá!",
	"Frenamos la charla pero la música no para. ¡Escuchate esto!",
	"¡Seguimos con más música!",
	"¡Que no decaiga!",
	"¡Pegale play que esto sigue!",
	"¡Metemos la próxima canción al toque!",
	"¡Seguimos de joda en La Rockola!",
	"¡Acomodate que se viene un temazo!",
	"¡Un carpinchazo de tema para vos; metele play!",
	"Tranqui en el agua, mate en mano... ¡a disfrutar lo que viene!",
	"¡Al pelo el ritmo; seguimos con todo en La Rockola!",
	"Posta, qué temazo se viene ahora; no te muevas de ahí.",
	"¡Basta de cháchara y que reviente el parche! ¡Metele play!",
	"¡Subile dos rayitas al volumen que este tema te levanta de la reposera!",
	"¡Agarrate fuerte de la borda que se viene un temazo al palo!",
	"¡A sacudirse el barro de las patas y meterle baile con esto que suena!",
	"¡Largá el remo un minuto y mandate a la pista con esta canción!",
	"¡Este tema te saca la fiaca de un tirón! ¡Dale gas!",
	"¡Temazo de aquellos para escuchar con la ventanilla baja y el viento en la cara!",
	"¡Dejate llevar por el compás que la tarde pide fiesta en la orilla!",
	"¡Volumen al mango que los carpinchos quieren cumbia!",
	"¡Acomodá el parlante mirando al río y disfrutá de este cañonazo musical!",
	# Presentando el "Próximo Tema"
	"Y ahora, un temazo que te va a hacer mover los muebles del living. ¡Ajustate los cinturones porque se viene un clásico de clásicos!",
	"Abrimos el arcón de los recuerdos en la Rockola. Subile el volumen a la radio, que este tema te va a hacer viajar en el tiempo.",
	"¿Querías ritmo? Tomá ritmo. A partir de este momento, se prohíbe quedarse sentado. ¡Que suene la música en la Rockola!",
	# Cierre de tanda / Separadores cortos
	"Pausa publicitaria en la mente, pero la música sigue acá. Estás en la Rockola.",
	# "¡Para Maru que nos escucha desde casa, te deseamos que tengas un buen día! ¡Un carpinchazo de tema para vos; cambiame la música!",
]

# ---------------------------------------------------------------------------
# Horas especiales en punto y segmentos modulares
# ---------------------------------------------------------------------------

SPECIAL_HOURS: dict[int, str] = {
	0: "Las doce de la noche en punto, arranca la trasnoche en La Rockola.",
	1: "Las una en punto, es hora de mimir.",
	2: "Las dos de la madrugada en punto, silencio en la laguna.",
	3: "Las tres de la mañana en punto, hora de los carpinchos sonámbulos.",
	4: "Las cuatro de la mañana en punto, el que no duerme pega en el palo.",
	5: "Las cinco de la mañana en punto, ya clarea en los bañados.",
	6: "Las seis de la mañana en punto, arriba que canta el chajá.",
	7: "Las siete de la mañana en punto, el agua está para unos buenos mates.",
	8: "Las ocho de la mañana en punto, arranca la jornada con toda la onda.",
	9: "Las nueve de la mañana en punto, el sol calienta la barranca.",
	10: "Las diez de la mañana en punto, una pastura tierna para picar.",
	11: "Las once de la mañana en punto, se siente el olorcito a comida.",
	12: "Las doce del mediodía en punto, hora de prender el fuego para el asado.",
	13: "Las una de la tarde en punto, la panza llena y el corazón contento.",
	14: "Las dos de la tarde en punto, sagrada hora de la siesta carpincha.",
	15: "Las tres de la tarde en punto, un chapuzón para refrescar las ideas.",
	16: "Las cuatro de la tarde en punto, salen esos mates con tortas fritas.",
	17: "Las cinco de la tarde en punto, la merienda no se negocia con nadie.",
	18: "Las seis de la tarde en punto, cae el solcito en el pajonal.",
	19: "Las siete de la tarde en punto, la tardecita pide buena música.",
	20: "Las ocho de la noche en punto, se va cerrando el boliche y abriendo la fiesta.",
	21: "Las nueve de la noche en punto, la mesa está servida en la madriguera.",
	22: "Las diez de la noche en punto, brindis con amigos y a disfrutar.",
	23: "Las once de la noche en punto, la última ronda antes de cerrar los ojales.",
}

HOUR_NAMES: list[str] = [
	"Las doce",
	"Las una",
	"Las dos",
	"Las tres",
	"Las cuatro",
	"Las cinco",
	"Las seis",
	"Las siete",
	"Las ocho",
	"Las nueve",
	"Las diez",
	"Las once",
]

MINUTE_SEGMENTS: list[str] = [
	"en punto.",
	"y cinco.",
	"y diez.",
	"y cuarto.",
	"y veinte.",
	"y veinticinco.",
	"y media.",
	"y treinta y cinco.",
	"menos veinte.",
	"menos cuarto.",
	"menos diez.",
	"menos cinco.",
]

# ---------------------------------------------------------------------------
# Clima: Lead-ins, condiciones y plantillas
# ---------------------------------------------------------------------------

DEFAULT_WEATHER_LOCATION: str = "San Miguel de Tucumán"
WEATHER_RAIN_THRESHOLD: int = 50

WEATHER_LEAD_INS: list[str] = [
	"El informe del tiempo carpincho nos canta la posta.",
	"Mirá por la ventana o pará la oreja, que así viene el clima.",
	"Atenti con el servicio meteorológico de La Rockola.",
	"Momento de chequear cómo viene la mano con el cielo.",
	"Pará un segundo el mate que te paso el parte meteorológico.",
	"Asomate a la orilla que te tiro los datos del cielo.",
	"Pará la oreja que acá está el pronóstico oficial de los bañados.",
	"Dejá la pava en el fuego un toque que te canto el tiempo en la zona.",
	"Antes de meter panzada al agua, chequeá cómo viene el clima.",
	"Atenti la muchachada con el reporte del tiempo recién salido del horno.",
]

WEATHER_TEMPLATES: list[str] = [
	# Plantilla 1: Directa y clásica
	"{lead} En {location}, tenemos {temp_str} de temperatura actual.{desc_phrase} Para hoy la mínima es de {min_today_str} y la máxima alcanzará los {max_today_str}. Para mañana esperamos {range_tomorrow_str}. {lluvia_desc}",
	# Plantilla 2: Centrada en la sensación térmica y perspectiva
	"{lead} Para {location}, la temperatura en este momento marca {temp_str}.{desc_phrase} Hoy el termómetro se moverá entre {min_today_str} de mínima y {max_today_str} de máxima. Mañana vamos a andar {range_tomorrow_str}. {lluvia_desc}",
	# Plantilla 3: Coloquial carpinchera
	"{lead} Clavamos {temp_str} en {location}.{desc_phrase} Para lo que queda del día esperamos entre {min_today_str} y {max_today_str}. Y ojo a mañana que esperamos {range_tomorrow_str}. {lluvia_desc}",
	# Plantilla 4: Costera / orilla
	"{lead} Reporte fresco desde {location}: el termómetro acusa {temp_str}.{desc_phrase} Para hoy calculamos entre {min_today_str} y {max_today_str}. Mañana nos espera {range_tomorrow_str}. {lluvia_desc}",
	# Plantilla 5: Enfocada en la jornada
	"{lead} Así pinta la cosa por {location}: tenemos {temp_str} de térmica.{desc_phrase} La mínima prevista para hoy ronda los {min_today_str} y la máxima trepará a {max_today_str}. Mañana andaremos {range_tomorrow_str}. {lluvia_desc}",
	# Plantilla 6: Radiofónica dinámica
	"{lead} Actualizamos los números del tiempo en {location}: clava {temp_str}.{desc_phrase} Hoy la marca irá de {min_today_str} a {max_today_str}. Y mirando a mañana, pronostican {range_tomorrow_str}. {lluvia_desc}",
]

PRECIPITATING_CATEGORIES: frozenset[str] = frozenset(
	{
		"blizzard",
		"drizzle",
		"freezing_drizzle",
		"hail",
		"heavy_rain",
		"light_rain",
		"moderate_rain",
		"sleet",
		"snow",
		"snow_thunder",
		"thunderstorm",
	}
)

RAIN_DESCRIPTIONS: dict[tuple[bool, bool], list[str]] = {
	(False, False): [
		"De lluvias ni hablemos: cero precipitaciones en el horizonte, ideal para unos buenos mates.",
		"Sin lluvias a la vista: no hay agua que amenace la jornada en la orilla.",
		"Cero agua en el horizonte: ni miras de precipitaciones para hoy ni para mañana.",
		"Olvidate del paraguas: el agua no dice presente y zafamos del chaparrón.",
		"El tiempo nos acompaña sin lluvias a la vista: jornada tranquila para relajarse y meter buena música.",
		"Sin una gota a la vista: tiempo seco en la zona para andar tranquilos en la barranca.",
	],
	(True, False): [
		"Atenti que hoy se esperan lluvias y chaparrones, pero mañana ya zafamos y mejora la cosa.",
		"Hoy toca mojarse con algunas lluvias en la zona, pero tranqui que mañana ya abre el cielo.",
		"Paraguas a mano para lo que queda de hoy porque el agua dice presente, aunque mañana ya mejora el panorama.",
		"Hoy nos toca chaparrón para regar los pastizales, pero mañana ya volvemos a secarnos al solcito.",
		"Atenti con los charcos hoy que viene con agua, pero mañana ya zafamos y sale el sol.",
		"Lluvias intermitentes para la jornada de hoy, pero mañana ya afloja y se compone el tiempo.",
	],
	(False, True): [
		"Hoy zafamos del agua, pero andá aprontando el paraguas porque mañana se vienen las lluvias.",
		"Por hoy zafamos tranquilos, pero ojo que mañana el cielo se viene con agua y chaparrones.",
		"Aprovechá la jornada seca de hoy, porque mañana el pronóstico nos promete agua a full.",
		"Hoy disfrutamos sin lluvia, pero andá teniendo a mano las botas que mañana se larga con ganas.",
		"Hoy zafamos de diez, pero guardá la ropa seca que mañana la lluvia no perdona.",
		"El cielo aguanta por hoy, pero mañana preparate para los chaparrones en la laguna.",
	],
	(True, True): [
		"Se vienen lluvias tanto para hoy como para mañana, ¡clima soñado para andar chapoteando en el agua!",
		"Agua para hoy y agua para mañana: los carpinchos chochos nadando en el arroyo crecido.",
		"El cielo no afloja: lluvias hoy y precipitaciones también mañana, ideal para tortas fritas y radio.",
		"Jornadas pasadas por agua hoy y mañana, ¡el bañado está de fiesta con tanta lluvia!",
		"Paraguas fijo para hoy y mañana: el agua no nos da tregua pero le ponemos onda con buena cumbia.",
		"Mucha agua en el radar para hoy y para mañana: ¡lindo temporal para quedarse al reparo escuchando música!",
	],
}

RAIN_NO_RAIN: list[str] = RAIN_DESCRIPTIONS[(False, False)]
RAIN_TODAY_ONLY: list[str] = RAIN_DESCRIPTIONS[(True, False)]
RAIN_TOMORROW_ONLY: list[str] = RAIN_DESCRIPTIONS[(False, True)]
RAIN_BOTH_DAYS: list[str] = RAIN_DESCRIPTIONS[(True, True)]

# ---------------------------------------------------------------------------
# Frases descriptivas del estado del cielo y tiempo según weatherDesc de wttr.in
# ---------------------------------------------------------------------------

WEATHER_CODE_TO_CATEGORY: dict[int, str] = {
	113: "sunny",
	116: "partly_cloudy",
	119: "cloudy",
	122: "overcast",
	143: "mist",
	176: "light_rain",
	179: "snow",
	182: "sleet",
	185: "freezing_drizzle",
	200: "thunderstorm",
	227: "blizzard",
	230: "blizzard",
	248: "fog",
	260: "fog",
	263: "drizzle",
	266: "drizzle",
	281: "freezing_drizzle",
	284: "freezing_drizzle",
	293: "light_rain",
	296: "light_rain",
	299: "moderate_rain",
	302: "moderate_rain",
	305: "heavy_rain",
	308: "heavy_rain",
	311: "sleet",
	314: "sleet",
	317: "sleet",
	320: "sleet",
	323: "snow",
	326: "snow",
	329: "snow",
	332: "snow",
	335: "snow",
	338: "snow",
	350: "hail",
	353: "light_rain",
	356: "heavy_rain",
	359: "heavy_rain",
	362: "sleet",
	365: "sleet",
	368: "snow",
	371: "snow",
	386: "thunderstorm",
	389: "thunderstorm",
	392: "snow_thunder",
	395: "snow_thunder",
}

WEATHER_DESC_TO_CATEGORY: dict[str, str] = {
	"sunny": "sunny",
	"clear": "sunny",
	"soleado": "sunny",
	"despejado": "sunny",
	"cielo despejado": "sunny",
	"partly cloudy": "partly_cloudy",
	"parcialmente nublado": "partly_cloudy",
	"intervalos nubosos": "partly_cloudy",
	"nubosidad parcial": "partly_cloudy",
	"cloudy": "cloudy",
	"nublado": "cloudy",
	"overcast": "overcast",
	"cielo cubierto": "overcast",
	"cubierto": "overcast",
	"encapotado": "overcast",
	"mist": "mist",
	"bruma": "mist",
	"neblina": "mist",
	"shallow mist": "mist",
	"bruma poco profunda": "mist",
	"fog": "fog",
	"niebla": "fog",
	"partial fog": "fog",
	"niebla parcial": "fog",
	"patches of fog": "fog",
	"bancos de niebla": "fog",
	"patches of fog in vicinity": "fog",
	"bancos de niebla en las cercanías": "fog",
	"shallow fog": "fog",
	"niebla poco profunda": "fog",
	"freezing fog": "fog",
	"niebla helada": "fog",
	"light freezing fog": "fog",
	"niebla helada ligera": "fog",
	"drizzle": "drizzle",
	"llovizna": "drizzle",
	"garua": "drizzle",
	"garúa": "drizzle",
	"light drizzle": "drizzle",
	"llovizna ligera": "drizzle",
	"patchy light drizzle": "drizzle",
	"llovizna ligera irregular": "drizzle",
	"llovizna ligera localizada": "drizzle",
	"freezing drizzle": "freezing_drizzle",
	"llovizna helada": "freezing_drizzle",
	"heavy freezing drizzle": "freezing_drizzle",
	"llovizna muy helada": "freezing_drizzle",
	"patchy freezing drizzle nearby": "freezing_drizzle",
	"llovizna helada localizada en las cercanías": "freezing_drizzle",
	"posible llovizna helada irregular": "freezing_drizzle",
	"patchy freezing drizzle possible": "freezing_drizzle",
	"patchy rain nearby": "light_rain",
	"lluvia localizada en las cercanías": "light_rain",
	"patchy rain possible": "light_rain",
	"posible lluvia irregular": "light_rain",
	"patchy light rain": "light_rain",
	"lluvia ligera irregular": "light_rain",
	"lluvia ligera localizada": "light_rain",
	"light rain": "light_rain",
	"lluvia ligera": "light_rain",
	"light rain shower": "light_rain",
	"chubasco de lluvia ligera": "light_rain",
	"shower": "light_rain",
	"chubasco": "light_rain",
	"light shower": "light_rain",
	"chubasco ligero": "light_rain",
	"shower in vicinity": "light_rain",
	"chubasco en las cercanías": "light_rain",
	"rain in vicinity": "light_rain",
	"lluvia en las cercanías": "light_rain",
	"rain": "light_rain",
	"lluvia": "light_rain",
	"lluvia dispersa": "light_rain",
	"moderate rain at times": "moderate_rain",
	"lluvia moderada a intervalos": "moderate_rain",
	"lluvia moderada ocasional": "moderate_rain",
	"moderate rain": "moderate_rain",
	"lluvia moderada": "moderate_rain",
	"heavy rain at times": "heavy_rain",
	"lluvia fuerte a intervalos": "heavy_rain",
	"lluvia fuerte ocasional": "heavy_rain",
	"heavy rain": "heavy_rain",
	"lluvia fuerte": "heavy_rain",
	"fuerte lluvia": "heavy_rain",
	"torrential rain shower": "heavy_rain",
	"chubasco torrencial": "heavy_rain",
	"moderate or heavy rain shower": "heavy_rain",
	"chubasco de lluvia moderada o fuerte": "heavy_rain",
	"rain shower": "heavy_rain",
	"aguacero": "heavy_rain",
	"rain shower in vicinity": "heavy_rain",
	"aguacero en las cercanías": "heavy_rain",
	"thundery outbreaks possible": "thunderstorm",
	"posibles brotes de tormentas": "thunderstorm",
	"thundery outbreaks nearby": "thunderstorm",
	"thundery outbreaks in nearby": "thunderstorm",
	"brotes de tormenta en las cercanías": "thunderstorm",
	"thunderstorm": "thunderstorm",
	"tormenta": "thunderstorm",
	"thunderstorm in vicinity": "thunderstorm",
	"tormenta en las cercanías": "thunderstorm",
	"light thunderstorm": "thunderstorm",
	"tormenta ligera": "thunderstorm",
	"patchy light rain with thunder": "thunderstorm",
	"lluvia ligera irregular con truenos": "thunderstorm",
	"lluvia ligera localizada con truenos en la zona": "thunderstorm",
	"moderate or heavy rain with thunder": "thunderstorm",
	"lluvia moderada o fuerte con truenos": "thunderstorm",
	"moderate or heavy rain in area with thunder": "thunderstorm",
	"lluvia moderada a fuerte con truenos en la zona": "thunderstorm",
	"rain with thunderstorm": "thunderstorm",
	"lluvia con tormenta": "thunderstorm",
	"heavy rain with thunderstorm": "thunderstorm",
	"fuerte lluvia con tormenta": "thunderstorm",
	"patchy light snow": "snow",
	"nieve ligera irregular": "snow",
	"nieve ligera localizada": "snow",
	"light snow": "snow",
	"nieve ligera": "snow",
	"patchy moderate snow": "snow",
	"nieve moderada irregular": "snow",
	"nieve moderada localizada": "snow",
	"moderate snow": "snow",
	"nieve moderada": "snow",
	"patchy heavy snow": "snow",
	"nieve pesada irregular": "snow",
	"nieve fuerte localizada": "snow",
	"heavy snow": "snow",
	"nieve pesada": "snow",
	"nieve fuerte": "snow",
	"snow": "snow",
	"nieve": "snow",
	"nevisca": "snow",
	"patchy snow possible": "snow",
	"patchy snow nearby": "snow",
	"nieve localizada en las cercanías": "snow",
	"light snow showers": "snow",
	"chubascos de nieve ligera": "snow",
	"moderate or heavy snow showers": "snow",
	"chubascos de nieve moderada o fuerte": "snow",
	"snow shower": "snow",
	"chubasco de nieve": "snow",
	"snow shower in vicinity": "snow",
	"chubasco de nieve en las cercanías": "snow",
	"heavy snow shower": "snow",
	"fuerte chubasco de nieve": "snow",
	"patchy sleet possible": "sleet",
	"posible aguanieve irregular": "sleet",
	"patchy sleet nearby": "sleet",
	"aguanieve localizada en las cercanías": "sleet",
	"light sleet": "sleet",
	"aguanieve ligera": "sleet",
	"moderate or heavy sleet": "sleet",
	"aguanieve moderada o fuerte": "sleet",
	"light sleet showers": "sleet",
	"chubascos de aguanieve ligera": "sleet",
	"moderate or heavy sleet showers": "sleet",
	"chubascos de aguanieve moderada o fuerte": "sleet",
	"light freezing rain": "sleet",
	"lluvia ligera helada": "sleet",
	"lluvia helada ligera": "sleet",
	"moderate or heavy freezing rain": "sleet",
	"lluvia helada moderada o fuerte": "sleet",
	"sleet": "sleet",
	"aguanieve": "sleet",
	"blowing snow": "blizzard",
	"nieve tormentosa": "blizzard",
	"ventiscas de nieve ligeras": "blizzard",
	"blizzard": "blizzard",
	"ventisca": "blizzard",
	"ice pellets": "hail",
	"perdigones de hielo": "hail",
	"gránulos de hielo": "hail",
	"granulos de hielo": "hail",
	"small hail/snow pallets": "hail",
	"granizo pequeño o nieve granulada ligera": "hail",
	"small hail/snow pallets shower": "hail",
	"chubasco de granizo pequeño o nieve granulada": "hail",
	"hail": "hail",
	"granizo": "hail",
	"patchy light snow with thunder": "snow_thunder",
	"nevada ligera irregular con truenos": "snow_thunder",
	"nieve ligera localizada con truenos en la zona": "snow_thunder",
	"moderate or heavy snow with thunder": "snow_thunder",
	"nevada moderada o fuerte con truenos": "snow_thunder",
	"moderate or heavy snow in area with thunder": "snow_thunder",
	"nieve moderada a fuerte con truenos en la zona": "snow_thunder",
	"snow with thunderstorm": "snow_thunder",
	"nieve con tormenta": "snow_thunder",
	"squalls": "wind_squalls",
	"rachas de tormenta": "wind_squalls",
	"smoke": "smoke_dust",
	"humo": "smoke_dust",
	"haze": "smoke_dust",
	"calina": "smoke_dust",
	"widespread dust": "smoke_dust",
	"polvo generalizado": "smoke_dust",
	"sand": "smoke_dust",
	"arena": "smoke_dust",
	"sandstorm": "smoke_dust",
	"tormenta de arena": "smoke_dust",
}

WEATHER_DESC_PHRASES: dict[str, list[str]] = {
	"sunny": [
		"Cielo completamente despejado y sol a pleno para secarse el lomo en la orilla.",
		"Sol radiante de punta a punta, ni una sola nube en el horizonte.",
		"Cielo limpito y solazo carpincho para disfrutar en la barranca.",
		"Sol brillante en todo el bañado, ideal para tirarse a la sombra de un ceibo.",
		"Cielo abierto y despejado con un sol que te templa el alma.",
		"Cielo azul impecable, una postal perfecta sobre el río.",
	],
	"partly_cloudy": [
		"Cielo parcialmente nublado, con el sol jugando a las escondidas entre las nubes.",
		"Intervalos de sol y nubes en el bañado, ideal para tomar unos mates tranqui.",
		"Cielo a medio cubrir, con ratos de solcito que asoma entre nubes ligeras.",
		"Parcialmente nublado sobre la laguna, ni muy tapado ni a pleno rayo.",
		"Nubes dispersas que van y vienen pero dejan pasar una linda claridad.",
		"Sol y nubes repartiéndose el cielo, tarde templada en el humedal.",
	],
	"cloudy": [
		"Cielo nublado y grisáceo sobre la cuenca, tarde tranquila con la radio sonando.",
		"Manta de nubes cubriendo la laguna, el sol se tomó un descanso.",
		"Completamente nublado en la zona, ideal para unos buenos amargos en la madriguera.",
		"Nubes bajas tapando el cielo, lindo día para quedarse al reparo escuchando música.",
		"Cielo bien gris y nublado en los bañados, pinta para meter tortas fritas.",
		"Nubes copando la parada por acá, tarde fresca y nublada.",
	],
	"overcast": [
		"Cielo encapotado y cerrado de par en par, no pasa ni un rayo de sol.",
		"Cielo completamente cubierto sobre el bañado, parece que se nos viene la noche antes de tiempo.",
		"Encapotado total en la ribera, una postal gris sobre el río.",
		"Cielo tapado hasta el cogote, el sol bien guardado tras las nubes.",
		"Manta gris pesada cubriendo todo el horizonte isleño.",
		"Cielo cerrado y encapotado, clima ideal para matear sin apuro.",
	],
	"mist": [
		"Bruma flotando sobre el agua que le da un toque misterioso a la orilla.",
		"Neblina mansa cubriendo los juncales, apenas si se divisa la otra orilla.",
		"Bruma húmeda en el aire que te moja hasta los bigotes.",
		"Vapor y bruma levantándose del río, paisaje típico de bañado.",
		"Neblina suavecita acariciando los pastizales de la laguna.",
		"Bruma baja que borra el horizonte del arroyo.",
	],
	"fog": [
		"Bancos de niebla espesa sobre el humedal, no se ve ni la proa de la canoa.",
		"Niebla cerrada en la cuenca, ¡ojo al piojo los que andan navegando!",
		"Mucha niebla sobre el agua, a prender los faroles y no apurarse.",
		"Niebla tupida cubriendo el arroyo, la laguna parece un fantasma.",
		"Visibilidad reducida por niebla cerrada en la zona, calma total en el río.",
		"Cerrada niebla en la barranca, el agua y el cielo parecen la misma cosa.",
	],
	"drizzle": [
		"Una garúa finita que moja despacito pero constante sobre el rancho.",
		"Llovizna suave en la zona, de esas que parece que no pero te calan el cuero.",
		"Garúa carpincha cayendo sobre el agua, ideal para tortas fritas.",
		"Llovizna mansa refrescando los juncos de la orilla.",
		"Gota a gota cae una garúa serena con olorcito a tierra mojada.",
		"Llovizna ligera y pareja, el bañado respira verde y fresco.",
	],
	"freezing_drizzle": [
		"Llovizna helada cayendo en la zona, un fresquete que te parte los huesos.",
		"Garúa congelada que escarcha el pasto, ¡a meterse a la cueva con mate hirviendo!",
		"Agua heladísima cayendo como aguja, los carpinchos bien abrigados.",
		"Llovizna con frío polar, ¡un invierno crudo en el bañado!",
		"Gotas heladas que escarchan la costa, el mate es obligatorio para no congelarse.",
		"Llovizna bajo cero congelando los pajonales, clima áspero en la ribera.",
	],
	"light_rain": [
		"Lluvia ligera y chaparrones suaves regando todo el pajonal.",
		"Lluvia mansa pero firme en los alrededores, levantando vapor de la tierra.",
		"Chubascos ligeros cayendo sobre la laguna, los carpinchos flotando chochos.",
		"Agua tranquila que cae del cielo, una lluvia suavecita para poner pausa y escuchar música.",
		"Lluvia dispersa por la zona, nada que asuste pero refresca lindo.",
		"Gotas suaves salpicando el río, lindo compás para acompañar la radio.",
	],
	"moderate_rain": [
		"Lluvia moderada y constante cayendo sobre todo el humedal.",
		"Chaparrones bien plantados en la zona, el río empieza a juntar agua.",
		"Lluvia pareja en la laguna, el bañado agradece cada gota.",
		"Chubascos intermitentes pero con buen ritmo, tarde mojada en la ribera.",
		"Lluvia firme sobre el pastizal, a disfrutar del sonido del agua contra el techo.",
		"Lluvia con ganas pero sin apuro, el arroyo va sumando caudal.",
	],
	"heavy_rain": [
		"Se vino la lluvia con ganas: agua fuerte azotando la laguna.",
		"Chaparrón intenso y lluvia torrencial, los carpinchos festejando en el agua.",
		"Cae agua a baldes sobre el humedal, temporal lindo para escuchar La Rockola bajo techo.",
		"Lluvia pesada y constante sobre la ribera, el río crece y la música acompaña.",
		"Lluvia fuerte y tupida, ¡afuera el barro es una fiesta!",
		"Aguacero bravo sobre los bañados, el agua corre que da calambre.",
	],
	"thunderstorm": [
		"Tormenta eléctrica con truenos retumbando en el bañado y relámpagos a lo lejos.",
		"Se picó el cielo: tormenta brava con truenos y chaparrones fuertes sobre la zona.",
		"Cielo rugiendo con tormenta y rayos, ¡a desenchufar lo delicado y meterle radio!",
		"Temporal con aparato eléctrico y truenos sonando fuerte en todo el humedal.",
		"Tormenta eléctrica en la zona, puro espectáculo de luces y agua en la cuenca.",
		"Truenos retumbando en la barranca y chaparrones eléctricos, ¡la tormenta se hace sentir!",
	],
	"snow": [
		"Cae nieve sobre la zona, una postal blanca impensada para los carpinchos.",
		"Copos de nieve blanqueando la barranca y el pajonal, ¡un frío polar total!",
		"Nevada firme en el paisaje, a meter poncho criollo y leña al fuego.",
		"Cielo blanco y nieve cubriendo la orilla, ¡para tomar chocolate caliente con tortas fritas!",
		"Nieve cayendo mansa en el bañado, un paisaje de película para disfrutar abrigado.",
		"Copos de nieve flotando sobre el río helado, postal insólita en la laguna.",
	],
	"sleet": [
		"Aguanieve helada cayendo del cielo, ¡un frío que te congela hasta las orejas!",
		"Lluvia helada y aguanieve golpeando en la orilla, a refugiarse en la madriguera.",
		"Mezcla de lluvia y nieve con viento helado, tiempo crudísimo en la cuenca.",
		"Aguanieve picando en el agua, los carpinchos pegaditos para darse calor.",
		"Hielo fino y agua helada cayendo de golpe, ¡abríguense bien los que anden afuera!",
		"Aguanieve persistente en la zona, el río parece escarchado.",
	],
	"blizzard": [
		"Ventisca brava con viento helado y nieve volando por todos lados.",
		"Tormenta de nieve y viento blanco, ¡no se ve un pito afuera!",
		"Temporal helado con ráfagas de nieve, a no asomar ni la nariz del rancho.",
		"Viento blanco azotando la orilla, a quedarse bien quietos en la cueva.",
		"Ventisca polar en el humedal, el viento silba entre las tacuaras.",
		"Tormenta de viento y nieve cerrada, las patas bajo techo hasta que aclare.",
	],
	"hail": [
		"Chubascos de granizo y gránulos de hielo repiqueteando en las chapas.",
		"Granizo menudo cayendo en la zona, ¡a guardar la canoa y ponerse a cubierto!",
		"Hielo picando en el agua de la laguna, los carpinchos protegidos bajo el ceibo.",
		"Piedra y granizo salpicando el bañado, ¡cuidado con la cabeza y los techos!",
		"Granizo sobre el río, el agua salpica como si hirviera.",
		"Piedra fina cayendo en el rancho, ¡a esperar que pase con unos buenos mates!",
	],
	"snow_thunder": [
		"Tormenta con truenos y nevada intensa, un fenómeno de locos en la laguna.",
		"Nieve acompañada de truenos lejanos, el cielo está que no cree en nadie.",
		"Temporal blanco con aparato eléctrico, clima bravo pero pintoresco.",
		"Nevada con rayos y truenos, ¡la naturaleza haciendo de las suyas en el bañado!",
		"Nieve y relámpagos cruzando el cielo gris, postal invernal única.",
		"Truenos en plena nevada, a resguardarse y disfrutar el calor del fogón.",
	],
	"wind_squalls": [
		"Rachas de viento fuerte sacudiendo los sauces de la ribera.",
		"Sudestada brava con viento arrachado levantando olas en el arroyo.",
		"Viento del este soplando con furia en el bañado, a amarrar bien los botes.",
		"Ráfagas intensas silbando entre los juncales, el río se pone picado.",
		"Viento fuerte barriendo la cuenca, ¡cuidado con las ramas secas!",
		"Viento arremolinado en la barranca, la sudestada se hace sentir.",
	],
	"smoke_dust": [
		"Ambiente turbio con humo y visibilidad reducida sobre la cuenca.",
		"Polvareda y calina flotando en el aire, a humedecer la garganta con unos buenos mates.",
		"Bruma seca y polvo en suspensión sobre los bañados, tarde densa en la ribera.",
		"Cielo opaco por humo y polvillo, a quedarse al reparo con la radio prendida.",
		"Visibilidad baja por polvo y calina en el ambiente, tarde pesada en la isla.",
		"Polvareda levantada por el viento seco, el horizonte se ve borroso.",
	],
	"default": [
		"Tiempo característico de humedal en la zona, ideal para acompañar con buena música.",
		"Así viene pintando el cielo por acá, con La Rockola haciéndote el aguante.",
		"El cielo desplegando su magia sobre la laguna para disfrutar la jornada.",
		"Clima isleño de pura cepa, perfecto para relajarse y meter play.",
		"Panorama ribereño inmejorable, la tranquilidad del agua nos acompaña.",
		"Condiciones ideales para bajar un cambio y dejarse llevar por el ritmo.",
	],
}


def resolve_weather_desc_category(
	desc: str | None = None,
	code: int | str | None = None,
	lang_es: str | None = None,
) -> str:
	"""
	Determina la categoría canónica del clima según weatherCode o weatherDesc de wttr.in.
	Prioriza el código numérico estándar WWO (weatherCode), luego lookup por texto exacto
	(inglés o español) y finalmente coincidencias léxicas/semánticas con fallback seguro.
	"""
	if code is not None:
		try:
			code_int = int(code)
			if code_int in WEATHER_CODE_TO_CATEGORY:
				return WEATHER_CODE_TO_CATEGORY[code_int]
		except (ValueError, TypeError):
			pass

	raw = lang_es or desc
	if not raw or not isinstance(raw, str) or not raw.strip():
		return ""

	norm = raw.strip().lower()
	if norm in WEATHER_DESC_TO_CATEGORY:
		return WEATHER_DESC_TO_CATEGORY[norm]

	# Búsqueda semántica por palabras clave
	if any(k in norm for k in ("thunder", "torment", "truen", "rayo")):
		return "snow_thunder" if any(k in norm for k in ("nieve", "snow", "nevad")) else "thunderstorm"
	if any(k in norm for k in ("blizzard", "ventisca")):
		return "blizzard"
	if any(k in norm for k in ("granizo", "hail", "pellet", "perdigon", "piedra")):
		return "hail"
	if any(k in norm for k in ("sleet", "aguanieve")):
		return "sleet"
	if any(k in norm for k in ("freezing", "helad")):
		return "freezing_drizzle"
	if any(k in norm for k in ("snow", "nieve", "nevad", "nevisc")):
		return "snow"
	if any(k in norm for k in ("torren", "heavy", "fuerte", "aguacero")):
		return "heavy_rain"
	if "modera" in norm:
		return "moderate_rain"
	if any(k in norm for k in ("drizzle", "garua", "garúa", "llovizn")):
		return "drizzle"
	if any(k in norm for k in ("rain", "shower", "lluvia", "chubasco")):
		return "light_rain"
	if any(k in norm for k in ("fog", "niebla")):
		return "fog"
	if any(k in norm for k in ("mist", "bruma", "neblina")):
		return "mist"
	if any(k in norm for k in ("overcast", "cubierto", "encapotado")):
		return "overcast"
	if any(k in norm for k in ("partly", "parcial", "intervalo")):
		return "partly_cloudy"
	if any(k in norm for k in ("cloud", "nublado", "nube")):
		return "cloudy"
	if any(k in norm for k in ("sun", "soleado", "clear", "despejado")):
		return "sunny"
	if any(k in norm for k in ("squall", "racha", "viento")):
		return "wind_squalls"
	if any(k in norm for k in ("smoke", "humo", "dust", "polvo", "sand", "arena", "haze", "calina")):
		return "smoke_dust"

	return "default"


def get_weather_desc_phrase(
	desc: str | None = None,
	code: int | str | None = None,
	lang_es: str | None = None,
	variant_idx: int | None = None,
) -> str:
	"""
	Retorna una frase descriptiva con impronta criolla para el estado actual del cielo
	según el weatherDesc, weatherCode o lang_es de wttr.in.
	Si no se proporcionan descripciones ni códigos válidos, retorna cadena vacía "".
	Si variant_idx se especifica, retorna esa variante determinista (variant_idx=0 es la clásica).
	Si variant_idx es None, elige una variante aleatoria.
	"""
	if not desc and code is None and not lang_es:
		return ""

	category = resolve_weather_desc_category(desc=desc, code=code, lang_es=lang_es)
	options = WEATHER_DESC_PHRASES.get(category, WEATHER_DESC_PHRASES["default"])
	if variant_idx is not None:
		return options[variant_idx % len(options)]
	return random.choice(options)


def get_all_weather_desc_phrases() -> list[str]:
	"""Devuelve la lista consolidada de todas las descripciones de cielo/tiempo posibles."""
	res: list[str] = []
	for p_list in WEATHER_DESC_PHRASES.values():
		for p in p_list:
			if p not in res:
				res.append(p)
	return res


# ---------------------------------------------------------------------------
# Charla de cabina: Pases y Reacciones
# ---------------------------------------------------------------------------

PASES_A_CLIMA: list[str] = [
	"Che {cohost}, asomate al bañado y decime si viene el pampero.",
	"{cohost}, ¿cómo está la temperatura para meter panzada al río?",
	"Tirame la data del cielo, {cohost}, que se me están enfriando las patas.",
	"Decime qué onda afuera, {cohost}, ¿sale mate caliente o tereré?",
	"A ver compadre {cohost}, cantame cómo pinta la mano meteorológica.",
	"Y para el tiempo, {cohost}, ¿cómo viene la mano?",
	"A ver, {cohost}, ¿qué nos canta el cielo hoy?",
	"{cohost}, tirate el parte meteorológico carpincho.",
	"¿Cómo viene la mano afuera, {cohost}?",
	"{cohost}, ¿salimos en cuero o aprontamos el paraguas?",
	"Contame qué dice el servicio meteorológico, {cohost}.",
	"¿Qué tenemos en el pronóstico para hoy, {cohost}?",
	"Che, {cohost}, ¿cómo pinta el clima en el bañado?",
	"Che {cohost}, con esta sudestada que amaga con subir el río, ¿qué dice el pronóstico?",
	"Decime {cohost}, con esta humedad que te riza hasta los bigotes, ¿se viene el chaparrón o zafamos?",
	"A ver {cohost}, asomate al muelle y decime si el viento del este nos trae agua.",
	"{cohost}, tirame la posta del tiempo: ¿está para meter panzada al río o nos refugiamos en la cueva?",
	"Che {cohost}, mirá cómo vuelan bajo las golondrinas... ¿qué marca el radar para hoy?",
	"Cantame los números del clima {cohost}, que la tarde está tan pesada que ni los mosquitos vuelan.",
	"¿Cómo viene la mano con el cielo {cohost}, sale sol para secar el cuero o preparamos el piloto?",
	"{cohost}, compadre de cabina, ¿cómo pinta el tiempo para los que andan navegando la cuenca?",
]

RADIO_HANDOFFS: list[str] = [
	"¿Cómo viene la mano afuera, che?",
	"Contame qué dice el servicio meteorológico.",
	"¿Qué tenemos en el pronóstico para hoy?",
	"Tirate esa data de la laguna.",
	"Pará que quiero saber qué dice el oráculo.",
	"¿Qué nos espera en el cielo, compadre?",
	"Tirame el parte meteorológico carpincho.",
]

REACCIONES_CLIMA: dict[str, list[str]] = {
	"calor": [
		"¡Mamita querida, qué calorón para estar en el agua todo el día!",
		"¡Hermoso para un chapuzón en la laguna con tereré!",
		"¡Pesadito el calor! No te olvides el protector solar.",
		"¡Está para quedarse a la sombra tomando mates fríos!",
		"¡Qué solazo! A buscar la sombrita del ceibo urgente.",
	],
	"frio": [
		"¡Fresquito para poncho! Metan más leña al fuego.",
		"¡Qué frescor, compadre! Salen esos mates bien calientes.",
		"¡Está para invernar abajo de la paja brava!",
		"¡Se vino el frío de golpe! A cuidar las orejas.",
		"¡Pucha que está fresco! Lindo para unas tortas fritas.",
	],
	"lluvia": [
		"¡Clima soñado de lluvia para andar chapoteando en el agua!",
		"¡Qué hermosura de agua! La laguna nos sonríe.",
		"¡Se viene el agua nomás! A disfrutar del olorcito a tierra mojada.",
		"¡Al pelo la lluvia para meter siesta carpincha!",
		"¡Chaparrón a la vista! El río va a estar una pinturita.",
	],
	"agradable": [
		"¡Una pinturita de día para andar al aire libre!",
		"¡Joya total! El clima ideal para unos amargos en la orilla.",
		"¡Ni frío ni calor, qué más querés para pasarla bomba!",
		"¡Clima perfecto, compadre! A disfrutarlo a pleno.",
		"¡Está de diez afuera! Ni una queja podemos meter.",
	],
}

REACCIONES_FORTUNA: list[str] = [
	"¡Olvídate! Mejor explicado, imposible.",
	"¡Uh, qué bárbaro! Me dejó recalculando.",
	"Tal cual, compadre... no le saques ni una coma.",
	"¡Mamita querida! Metiste el dedo en la llaga.",
	"Naaa, qué momento. Piel de carpincho se me puso.",
	"Tranqui, fiera... que no cunda el pánico en el pajonal.",
	"¡Qué personaje! Firmo abajo.",
	"¡Ja! Qué sabio el oráculo.",
	"¡Tal cual, compadre! La pura verdad.",
	"¡Qué lo tiró! Sabiduría pura de la laguna.",
	"¡Amén! Más claro, echale agua.",
	"¡Posta! Tomá nota de esa.",
	"¡Ojo al piojo! No tiene desperdicio.",
	"¡Una joyita de reflexión!",
	"¡Mirá vos! Justo lo que hacía falta escuchar.",
	"¡Palabra santa! A guardarla en el corazón.",
	"¡De una! Nada más que agregar.",
	"¡Clarito como agua de arroyo en bajante!",
	"¡Naaa, qué filósofo de bañado tenemos hoy!",
	"¡Aplaudo de pie con las dos patas delanteras!",
	"¡Esa frase te acomoda las ideas de una sola cebada!",
	"¡Una obra de arte! Ni un poeta del Delta lo decía mejor.",
	"¡Totalmente! Guardalo en un frasco de mermelada y no lo pierdas.",
	"¡Qué profundidad criolla! Me quedé sin palabras, compadre.",
	"¡Eso no fue un consejo, fue una caricia al alma!",
	"¡Para ponerlo en un cartelito de madera en la entrada del rancho!",
	"¡Posta pura! Al que no le guste, que vaya a rumiar pasto amargo.",
]

REACCIONES_AVISOS: list[str] = [
	"¡Buen dato para los vecinos de la zona!",
	"Excelente servicio a la comunidad, como siempre en La Rockola.",
	"A tenerlo muy en cuenta la muchachada de la orilla.",
	"Ojo al piojo los que anden por ahí, tomen nota.",
	"¡Comercio y comunidad de primera en el humedal!",
	"¡Qué gran servicio! Siempre atentos a lo que pasa en el pago.",
	"Dato clave para no quedarse a pata en el río.",
]

REACCIONES_OYENTES: list[str] = [
	"¡Un abrazo gigante para toda esa linda gente que hace el aguante!",
	"¡Qué temazo que pidieron, ya mismo se lo mandamos al aire!",
	"¡Saludos a la barra y gracias por acompañarnos siempre!",
	"¡Al pelo ese mensaje, aguante la audiencia carpincha!",
	"¡Música y mate para todos ellos, que se sientan como en casa!",
	"¡Gente laburadora y de primera sintonizando La Rockola!",
	"¡Un saludo cariñoso para toda la muchachada que escucha!",
]

REACCIONES_ALERTAS: list[str] = [
	"¡Qué lo tiró, che! A prender el espiral y cerrar las ventanas.",
	"¡Mamita querida, qué plaga brava! A refugiarse en la cueva.",
	"¡A ponerle el pecho con un buen tereré y paciencia de carpincho!",
	"¡Cosas de nuestra tierra querida, a no aflojarle!",
	"¡Terrible situación! Aguanten los trapos que ya va a pasar.",
	"¡Paciencia criolla que después de la siesta afloja!",
]

REACCIONES_BY_CATEGORY: dict[str, list[str]] = {
	"fortuna": REACCIONES_FORTUNA,
	"aviso": REACCIONES_AVISOS,
	"oyentes": REACCIONES_OYENTES,
	"alerta_criolla": REACCIONES_ALERTAS,
}

RADIO_REACTIONS: list[str] = [
	"¡Qué lo tiró, che!",
	"Mirá vos, qué momento.",
	"Lindo momento para unos buenos mates.",
	"Una pinturita.",
	"Totalmente, compadre.",
	"Tal cual, fiera.",
	"¡Qué temazo metiste!",
	"La posta pura.",
	"¡Ojo al piojo!",
	"Así se habla en el pago.",
	"¡Qué pedazo de tema, por favor!",
	"Ese solo te afloja hasta las junturas.",
	"¡Inolvidable! Para escucharlo en loop todo el domingo.",
	"¡Qué ritmo sabroso, compadre!",
	"Te deja con el corazón saltando como boga en la red.",
	"¡Una locura total! Música de la buena.",
	"Ese tema te levanta cualquier día nublado.",
	"¡Qué swing ribereño metió esa banda!",
]

# ---------------------------------------------------------------------------
# NLP: Stopwords, Detección de Idioma y Verbos
# ---------------------------------------------------------------------------

KNOWN_SPANISH_DBS: set[str] = {
	"amistad",
	"argentina",
	"arte",
	"artistas",
	"asimov",
	"chistes",
	"ciencia",
	"citas",
	"deprimente",
	"es",
	"es-ar",
	"es-la",
	"familia",
	"famosos",
	"filosofia",
	"folklore",
	"humanos",
	"humor",
	"informatica",
	"lao-tse",
	"lemas",
	"leydemurphy",
	"libertad",
	"literatura",
	"nietzsche",
	"pintadas",
	"poder",
	"proverbios",
	"refranes",
	"sabiduria",
	"schopenhauer",
	"sentimientos",
	"tango",
	"varios",
	"varios-pre",
	"verdad",
	"vida",
}

SPANISH_CHARS: set[str] = set("áéíóúüñÁÉÍÓÚÜÑ¿¡")

# Lista cerrada y compacta de stopwords esenciales (preposiciones, artículos y palabras funcionales)
COMMON_SPANISH_WORDS: set[str] = {
	# Artículos y contracciones
	"al",
	"del",
	"el",
	"la",
	"las",
	"lo",
	"los",
	"un",
	"una",
	"unas",
	"unos",
	# Preposiciones esenciales
	"a",
	"ante",
	"bajo",
	"con",
	"contra",
	"de",
	"desde",
	"durante",
	"en",
	"entre",
	"hacia",
	"hasta",
	"mediante",
	"para",
	"por",
	"según",
	"sin",
	"sobre",
	"tras",
	# Pronombres y conectores frecuentes
	"como",
	"cuando",
	"donde",
	"e",
	"este",
	"esta",
	"esto",
	"le",
	"les",
	"me",
	"mi",
	"mis",
	"muy",
	"no",
	"nos",
	"o",
	"pero",
	"que",
	"quien",
	"se",
	"si",
	"su",
	"sus",
	"tan",
	"te",
	"tu",
	"tus",
	"u",
	"y",
	"ya",
}

COMMON_ENGLISH_WORDS: set[str] = {
	"about",
	"all",
	"an",
	"and",
	"are",
	"as",
	"at",
	"be",
	"been",
	"but",
	"by",
	"call",
	"can",
	"come",
	"could",
	"day",
	"did",
	"do",
	"down",
	"each",
	"find",
	"first",
	"for",
	"from",
	"get",
	"go",
	"had",
	"has",
	"have",
	"he",
	"her",
	"him",
	"his",
	"how",
	"i",
	"if",
	"in",
	"into",
	"is",
	"it",
	"its",
	"like",
	"look",
	"made",
	"make",
	"many",
	"may",
	"more",
	"my",
	"no",
	"not",
	"now",
	"number",
	"on",
	"one",
	"or",
	"other",
	"out",
	"part",
	"people",
	"said",
	"see",
	"she",
	"so",
	"some",
	"than",
	"that",
	"the",
	"their",
	"them",
	"then",
	"there",
	"these",
	"they",
	"this",
	"time",
	"two",
	"up",
	"use",
	"was",
	"water",
	"way",
	"we",
	"were",
	"what",
	"when",
	"which",
	"who",
	"will",
	"with",
	"would",
	"write",
	"you",
	"your",
}

# Raíces verbales de alta frecuencia para compactación morfológica
COMMON_VERB_ROOTS: set[str] = {
	"abraz",
	"acomod",
	"afirm",
	"alcanz",
	"am",
	"and",
	"anunc",
	"apag",
	"aparec",
	"aprend",
	"apur",
	"arm",
	"arranc",
	"arregl",
	"asombr",
	"avis",
	"ayud",
	"bail",
	"baj",
	"bast",
	"beb",
	"brill",
	"busc",
	"calent",
	"cambi",
	"camin",
	"cant",
	"cerr",
	"charl",
	"cobij",
	"com",
	"comenz",
	"compart",
	"compet",
	"compit",
	"compr",
	"concluy",
	"conoc",
	"consegu",
	"cont",
	"cop",
	"corr",
	"cre",
	"crec",
	"cruz",
	"cuid",
	"cumpl",
	"cur",
	"dej",
	"descans",
	"despein",
	"despert",
	"devolv",
	"disfrut",
	"dud",
	"dur",
	"ech",
	"empez",
	"encontr",
	"enseñ",
	"entend",
	"entr",
	"escuch",
	"esper",
	"explic",
	"extrañ",
	"falt",
	"fij",
	"flot",
	"fren",
	"gan",
	"gir",
	"goz",
	"guard",
	"gust",
	"habl",
	"honr",
	"import",
	"invit",
	"jug",
	"junt",
	"juzg",
	"larg",
	"lav",
	"levant",
	"limpi",
	"llor",
	"lleg",
	"llev",
	"madrug",
	"mand",
	"manej",
	"maravill",
	"mat",
	"mejor",
	"met",
	"mezcl",
	"mir",
	"nad",
	"necesit",
	"nombr",
	"not",
	"ocult",
	"odi",
	"olvid",
	"orden",
	"pag",
	"par",
	"parec",
	"part",
	"pas",
	"pele",
	"pens",
	"perdon",
	"perdid",
	"pes",
	"pic",
	"pint",
	"pregunt",
	"prend",
	"prob",
	"qued",
	"quem",
	"reaccion",
	"recib",
	"record",
	"reflexion",
	"regal",
	"relaj",
	"rem",
	"respir",
	"result",
	"romp",
	"sac",
	"salt",
	"salv",
	"sec",
	"sent",
	"separ",
	"sirv",
	"sobr",
	"solt",
	"sonre",
	"sufr",
	"sum",
	"tap",
	"tem",
	"termin",
	"tir",
	"toc",
	"tom",
	"trabaj",
	"trat",
	"un",
	"viaj",
	"viv",
	"vol",
}

# Verbos irregulares y auxiliares esenciales (haber, ser, estar, ir, tener, hacer, dar, ver, poder, deber y afines)
AUXILIARY_AND_IRREGULAR_VERBS: set[str] = {
	# haber
	"ha",
	"han",
	"has",
	"he",
	"hemos",
	"hay",
	"haya",
	"hayan",
	"había",
	"habían",
	"hubo",
	"hubieron",
	"habrá",
	"habrán",
	"haber",
	# ser
	"es",
	"era",
	"eran",
	"éramos",
	"eras",
	"fue",
	"fueron",
	"fui",
	"fuiste",
	"sea",
	"sean",
	"seamos",
	"somos",
	"son",
	"sos",
	"soy",
	"ser",
	"será",
	"serán",
	"sería",
	"serían",
	"siendo",
	"sido",
	# estar
	"está",
	"están",
	"estás",
	"estamos",
	"estoy",
	"esté",
	"estén",
	"estaba",
	"estaban",
	"estuvo",
	"estuvieron",
	"estará",
	"estarán",
	"estar",
	"estando",
	"estado",
	# ir
	"va",
	"van",
	"vas",
	"vamos",
	"voy",
	"vaya",
	"vayan",
	"iba",
	"iban",
	"irá",
	"irán",
	"irás",
	"iremos",
	"ir",
	"yendo",
	"ido",
	# tener
	"tiene",
	"tienen",
	"tienes",
	"tenés",
	"tengo",
	"tenemos",
	"tenga",
	"tengan",
	"tenía",
	"tenían",
	"tuvo",
	"tuvieron",
	"tendrá",
	"tendrán",
	"tendré",
	"tener",
	"tenido",
	"teniendo",
	# hacer
	"hace",
	"hacen",
	"haces",
	"hacés",
	"hago",
	"hacemos",
	"haga",
	"hagan",
	"hacía",
	"hacían",
	"hizo",
	"hicieron",
	"hará",
	"harán",
	"haré",
	"hacé",
	"hacer",
	"hecho",
	"haciendo",
	# dar
	"da",
	"dan",
	"das",
	"damos",
	"doy",
	"dé",
	"den",
	"daba",
	"daban",
	"dio",
	"dieron",
	"dará",
	"darán",
	"daré",
	"dar",
	"dando",
	"dado",
	# ver
	"ve",
	"ven",
	"ves",
	"vemos",
	"veo",
	"vea",
	"vean",
	"veía",
	"veían",
	"vio",
	"vieron",
	"verá",
	"verán",
	"verás",
	"ver",
	"visto",
	"viendo",
	# poder
	"puede",
	"pueden",
	"puedes",
	"podés",
	"puedo",
	"podemos",
	"pueda",
	"puedan",
	"podía",
	"podían",
	"pudo",
	"pudieron",
	"podrá",
	"podrán",
	"poder",
	"podido",
	"pudiendo",
	# deber
	"debe",
	"deben",
	"debes",
	"debés",
	"debo",
	"debemos",
	"deba",
	"deban",
	"debía",
	"debían",
	"debió",
	"debieron",
	"deberá",
	"deberán",
	"deber",
	"debido",
	"debiendo",
	# decir, saber, querer, poner, venir, salir, traer, oír, caer, morir, dormir, valer, seguir
	"dice",
	"dicen",
	"dices",
	"decís",
	"digo",
	"decimos",
	"diga",
	"digan",
	"decía",
	"decían",
	"dijo",
	"dijeron",
	"dirá",
	"dirán",
	"decir",
	"dicho",
	"sabe",
	"saben",
	"sabes",
	"sabés",
	"sé",
	"sabemos",
	"sepa",
	"sepan",
	"sabía",
	"sabían",
	"supo",
	"supieron",
	"sabrá",
	"sabrán",
	"saber",
	"quiere",
	"quieren",
	"quieres",
	"querés",
	"quiero",
	"queremos",
	"quiera",
	"quieran",
	"quería",
	"querían",
	"quiso",
	"quisieron",
	"querrá",
	"querrán",
	"querer",
	"pone",
	"ponen",
	"pones",
	"ponés",
	"pongo",
	"ponemos",
	"ponga",
	"pongan",
	"ponía",
	"ponían",
	"puso",
	"pusieron",
	"pondrá",
	"pondrán",
	"poné",
	"poner",
	"puesto",
	"viene",
	"vienen",
	"vienes",
	"venís",
	"vengo",
	"venimos",
	"venga",
	"vengan",
	"venía",
	"venían",
	"vino",
	"vinieron",
	"vendrá",
	"vendrán",
	"venir",
	"sale",
	"salen",
	"sales",
	"salís",
	"salgo",
	"salimos",
	"salga",
	"salgan",
	"salía",
	"salían",
	"salió",
	"salieron",
	"saldrá",
	"saldrán",
	"salir",
	"trae",
	"traen",
	"traes",
	"traés",
	"traigo",
	"traemos",
	"traiga",
	"traigan",
	"traía",
	"traían",
	"trajo",
	"trajeron",
	"traer",
	"oye",
	"oyen",
	"oyó",
	"oído",
	"oír",
	"cae",
	"caen",
	"caía",
	"cayó",
	"cayeron",
	"caer",
	"muere",
	"mueren",
	"murió",
	"murieron",
	"morir",
	"muerto",
	"duerme",
	"duermen",
	"durmió",
	"durmieron",
	"dormir",
	"vale",
	"valen",
	"valió",
	"valer",
	"sirve",
	"sirven",
	"sirvió",
	"sigue",
	"siguen",
	"siguió",
	"seguir",
	"suena",
	"suenan",
	"sonó",
	"sonar",
	"vuela",
	"vuelan",
	"voló",
	"volar",
	"vuelve",
	"vuelven",
	"volvió",
	"volver",
	"pide",
	"piden",
	"pidió",
	"pedir",
}

# Combinación compacta de auxiliares/irregulares y formas regulares de alta frecuencia
COMMON_SPANISH_VERBS: set[str] = AUXILIARY_AND_IRREGULAR_VERBS.union(
	{
		f"{root}{suffix}"
		for root in COMMON_VERB_ROOTS
		for suffix in (
			"a",
			"e",
			"an",
			"en",
			"as",
			"es",
			"ás",
			"és",
			"ís",
			"á",
			"é",
			"í",
			"ate",
			"ete",
			"ite",
			"ale",
			"ele",
			"ile",
			"amos",
			"emos",
			"imos",
			"aba",
			"aban",
			"abas",
			"ábamos",
			"ía",
			"ían",
			"ías",
			"íamos",
			"ó",
			"ió",
			"aron",
			"ieron",
			"aste",
			"iste",
			"ará",
			"arán",
			"erá",
			"erán",
			"irá",
			"irán",
			"aría",
			"arían",
			"ería",
			"erían",
			"iría",
			"irían",
			"ar",
			"er",
			"ir",
			"ando",
			"iendo",
		)
	}
) - {"como", "para", "sobre", "ante", "bajo", "entre", "tras", "medio"}

VERBAL_SUFFIXES_REGEX = re.compile(
	r"^[a-záéíóúñ]{3,}(?:"
	# Voseo y enclíticos rioplatenses / criollos (-ás, -és, -ís, -ate, -ete, -ite)
	r"ás|és|ís|ate|ete|ite|"
	# Pretéritos perfectos e imperfectos
	r"aron|ieron|aste|iste|aban|abas|ábamos|abais|aba|"
	r"ieron|ieras|iéramos|ierais|ieran|iera|"
	r"ían|ías|íamos|íais|ía|"
	# Pretérito indefinido con tilde (-ó, -ió)
	r"ió|ó|"
	# Futuro
	r"arán|arás|ará|aremos|arais|"
	r"erán|erás|erá|eremos|erais|"
	r"irán|irás|irá|iremos|irais|"
	# Condicional
	r"arían|arías|aría|aríamos|aríais|"
	r"erían|erías|ería|eríamos|eríais|"
	r"irían|irías|iría|iríamos|iríais|"
	# Subjuntivo
	r"áramos|iéramos|ásemos|iésemos|asen|iesen|ase|iese|ases|ieses|"
	# Gerundio
	r"ando|iendo|yendo"
	r")$",
	re.IGNORECASE,
)

FORBIDDEN_FORMAT_CHARS: set[str] = set(r"*\/|+=>%^~@#$_[]{}&")

# ---------------------------------------------------------------------------
# Blacklist: Mal gusto y Jerga IA/Robot
# ---------------------------------------------------------------------------

PROFANITY_TERMS: set[str] = {
	# "boluda",
	# "boludas",
	# "boludo",
	# "boludos",
	# "cabron",
	# "cabrón",
	# "cabrones",
	# "carajo",
	# "carajos",
	# "chingada",
	# "chingar",
	"chota",
	"chotas",
	# "choto",
	# "chotos",
	# "chupala",
	"concha",
	"conchas",
	"conchuda",
	"conchudas",
	"conchudo",
	"conchudos",
	# "culiada",
	# "culiadas",
	# "culiado",
	# "culiados",
	# "culiao",
	# "culiaos",
	# "culo",
	# "culos",
	# "estupida",
	# "estúpida",
	# "estupidas",
	# "estúpidas",
	# "estupido",
	# "estúpido",
	# "estupidos",
	# "estúpidos",
	"forra",
	"forras",
	"forro",
	"forros",
	# "imbecil",
	# "imbécil",
	# "imbeciles",
	# "imbéciles",
	"malparida",
	"malparido",
	# "mamada",
	# "mamadas",
	"maricon",
	"maricón",
	"maricones",
	"mierda",
	"mierdas",
	"ojete",
	"ojetes",
	"orto",
	"ortos",
	"pelotuda",
	"pelotudas",
	"pelotudo",
	"pelotudos",
	# "pendeja",
	# "pendejas",
	# "pendejo",
	# "pendejos",
	"pija",
	"pijas",
	"puta",
	"putas",
	"puto",
	"putos",
	"sorete",
	"soretes",
	"tarada",
	"taradas",
	"tarado",
	"tarados",
	# "verga",
	# "vergas",
}

PROFANITY_PHRASES: list[str] = [
	"hijo de puta",
	"hija de puta",
	"hijos de puta",
	"hdp",
	"la puta madre",
	"la concha de",
	"andate a la mierda",
	"la puta que te",
]

AI_ROBOTIC_PHRASES: list[str] = [
	"como modelo de lenguaje",
	"como un modelo de lenguaje",
	"modelo de lenguaje",
	"en que puedo ayudarte",
	"en qué puedo ayudarte",
	"en qué puedo asistirte",
	"en que puedo asistirte",
	"procesando datos",
	"sistema operativo",
	"algoritmo",
	"algoritmos",
	"error 404",
	"404 not found",
	"código de error",
	"inteligencia artificial",
	"red neuronal",
	"redes neuronales",
	"asistente virtual",
	"asistente de ia",
	"asistente ia",
	"open ai",
	"openai",
	"chatgpt",
	"deepmind",
	"prompt",
	"prompts",
	"lenguaje de programación",
	"nullpointerexception",
	"segmentation fault",
	"stack overflow",
]


def resolve_segment_category(text: str) -> str:
	"""
	Clasifica el contenido radial en su categoría semántica:
	- 'oyentes': dedicatorias y pedidos de oyentes por WhatsApp/audio.
	- 'aviso': tanda publicitaria comercial, avisos parroquiales y tránsito fluvial.
	- 'alerta_criolla': reportes satíricos de clima extremo, mosquitos y viento norte.
	- 'fortuna': refranes, proverbios, máximas y reflexiones filosóficas.
	"""
	if not text or not isinstance(text, str):
		return "fortuna"
	text_clean = text.strip()
	text_lower = text_clean.lower()

	# 1. Oyentes (mensajes de WhatsApp, audios, pedidos de temas)
	if (
		text_clean in DEDICATORIAS_OYENTES
		or any(
			text_clean.startswith(p)
			for p in ("WhatsApp", "Llega audio", "Mensajito", "Audio de", "Nos escriben", "Llega mensaje")
		)
		or any(
			k in text_lower
			for k in (
				"whatsapp",
				"audio de",
				"mandale un abrazo",
				"pide un chamamé",
				"piden cumbia",
				"piden cuarteto",
				"pedimos cumbia",
				"pedimos cuarteto",
				"que suene gilda",
			)
		)
	):
		return "oyentes"

	# 2. Alertas criollas (mosquitos, jejenes, clima molesto)
	if text_clean in ALERTAS_INCOMODIDAD_CRIOLLA or any(
		k in text_lower
		for k in (
			"mosquito",
			"jejenes",
			"viento zonda",
			"viento norte",
			"humedad del 100%",
			"plaga de",
			"calor de siesta",
			"asfalto parece goma",
		)
	):
		return "alerta_criolla"

	# 3. Avisos comerciales, parroquiales, comunitarios y tránsito fluvial
	if (
		text_clean in CARPINCHO_ADS
		or text_clean in AVISOS_PARROQUIALES_Y_EXTRAVIOS
		or text_clean in TRANSITO_FLUVIAL_Y_CAMINOS
		or any(
			text_clean.startswith(p)
			for p in (
				"Espacio publicitario",
				"Publicidad",
				"Aviso ",
				"Se busca ",
				"Atención vecinos",
				"Lancha colectiva",
				"Balsa ",
				"Corte de ruta",
				"Alerta de tránsito",
				"Tránsito ",
				"Camino ",
				"Reporte de caminos",
				"Solidaridad ",
				"Objeto perdido",
				"Objeto hallado",
				"Extravío ",
				"Pérdida ",
				"Urgente del pueblo",
				"Demoras en ",
				"Estado de caminos",
			)
		)
		or any(
			k in text_lower
			for k in (
				"gomería",
				"ferretería",
				"emparchamos",
				"precios populares",
				"aviso comercial",
				"aviso parroquial",
				"se extravió",
				"se busca",
				"recompensa",
				"lancha colectiva",
				"tránsito fluvial",
				"puente viejo",
				"terraplén",
				"camino de ripio",
				"balsa maroma",
				"banco de arena",
				"barro greda",
			)
		)
	):
		return "aviso"

	return "fortuna"


def get_lead_ins_for_category(category: str) -> list[str]:
	"""Devuelve los lead-ins pertinentes a la categoría del segmento."""
	return LEAD_INS_BY_CATEGORY.get(category, LEAD_INS_FORTUNA)


def get_reactions_for_category(category: str) -> list[str]:
	"""Devuelve las reacciones de cabina pertinentes a la categoría del segmento."""
	return REACCIONES_BY_CATEGORY.get(category, REACCIONES_FORTUNA)
