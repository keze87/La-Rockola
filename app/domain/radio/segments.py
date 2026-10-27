"""
Estructura de segmentos radiales: intros, lead-ins, horas, cierres (outros), pases y reacciones.
"""

from __future__ import annotations

from app.domain.radio.phrase_banks.listeners import SEPARADORES_Y_SLOGANS

BASE_RADIO_INTROS: tuple[str, ...] = (
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
	"¡Atenti todo el mundo! Acomodá la silla, cebate un amargo y dejate llevar porque arranca otra tanda en La Rockola.",
	"¡Buenas y santas gente! Micrófonos listos, consola al palo y la mejor selección musical para alegrarte el rato.",
	"¡Agarrate fuerte que la playlist de hoy viene salteada! Acá no hay etiqueta que valga, solo buena música para el corazón.",
	"Se viene una tanda de esas bien ensaladas: un poco de esto, un poco de aquello y cero prejuicios. ¡Prendete a La Rockola!",
	# El arranque y la energía de la mañana
	"¡Sintonía total en todo el país! Estás en la Rockola del Carpincho, donde la música no para y los carpinchos tampoco. ¡{saludo} para todos!",
	"¡Arriba, arriba, arriba! Subí el volumen que si el vecino se queja, lo invitamos a tomar unos mates. ¡Arrancamos otra hora de puros éxitos!",
	"Estás escuchando la Rockola del Carpincho. Conduce quien les habla, musicaliza el destino, y del otro lado... ¡la mejor audiencia del planeta!",
	"¡Hola, hola! Reportándonos en vivo desde el mejor rincón del dial. Si estás yendo a laburar, paciencia; si estás volviendo, ¡sos un héroe nacional!",
	# Cierre de tanda / Separadores cortos
	"La Rockola del Carpincho: tu dosis diaria de música, mates y buena onda. No aceptes imitaciones.",
	# Transiciones secas y surrealistas
	"Interferencia en el canal cinco... restablecemos la señal. La Rockola está en el aire.",
	"Aviso críptico de cabina: el zorro vuela de noche con poncho azul. Y ahora, música.",
	"Silencio en el bajo. Escuchá lo que se viene.",
	"Sin rodeos: consola prendida, dial sintonizado y tema puesto.",
	"Directo al hueso. Así suena La Rockola.",
)
RADIO_INTROS: tuple[str, ...] = (*BASE_RADIO_INTROS, *SEPARADORES_Y_SLOGANS)

LEAD_INS_FORTUNA: tuple[str, ...] = (
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
)

LEAD_INS_AVISOS: tuple[str, ...] = (
	"Espacio publicitario en La Rockola.",
	"Atenti a este aviso de la comunidad carpinchera.",
	"Mensaje de nuestros queridos auspiciantes.",
	"Aviso importante de la vecindad de los bañados.",
	"Atendé lo que nos bajó la capitanía de la laguna.",
	"Llegó un aviso urgente a la mesa de control; pará la oreja:",
	"Parte comunitario y comercial en el aire de La Rockola:",
	"Avisos parroquiales y novedades de la cuenca; tomá nota:",
	"Llegó un mensaje en botella al terraplén; escuchá...",
)

LEAD_INS_OYENTES: tuple[str, ...] = (
	"Suena la campanita de mensajes en cabina; escuchate este:",
	"Bandeja de mensajes hasta las manos en La Rockola; atendé:",
	"Llegó un audio de WhatsApp a la consola; mirá lo que piden:",
	"Mensaje de la muchachada que nos acompaña del otro lado:",
	"Pará la oreja que los oyentes mandan reporte en vivo:",
	"Revisando los mensajes del pueblo en La Rockola; escuchá:",
	"La audiencia se hace sentir en el WhatsApp de la radio; atendé:",
)

LEAD_INS_ALERTAS: tuple[str, ...] = (
	"Reporte urgente desde la costa; ojo al piojo:",
	"Nos llega este parte especial desde las islas:",
	"Corresponsalía fluvial nos manda este flash, escuchá:",
	"Así están las cosas río abajo, nos cuentan desde la otra orilla:",
	"Cable urgente que nos tira la gente del litoral:",
	"Parte que nos acerca la posta del bañado, allá lejos:",
	"Reporte que nos envían desde los canales de navegación ribereños:",
)

LEAD_INS_CHISMES: tuple[str, ...] = (
	"Atenti que se picó en el humedal... ¡momento de radio pasillo y chismes carpincheros!",
	"Se filtró información clasificada de la madriguera; pará la oreja que esto quema:",
	"Esto no te lo cuentan en ningún documental de fauna... escuchate este chisme secreto:",
	"Radio conventillo ribereño: lo que los carpinchos no quieren que nadie sepa:",
	"¡Escándalo en el bañado! Nos llegó data pesada y sin filtro directo del pajonal:",
	"Ojo al piojo que rompemos el pacto de silencio de la laguna con esta bomba:",
	"Se pudrió todo en la orilla: mirá la data confidencial que rescatamos del arroyo:",
	"Desempolvamos el archivo prohibido del Delta... atendé a lo que salió a la luz:",
)

LEAD_INS_NOVELA: tuple[str, ...] = (
	"¡Atención vecindario! Se picó en el almacén y volaron los trapitos al sol... pará la oreja:",
	"Radio pasillo barrial al rojo vivo: lo que Doña Gladys y Don Anselmo no querían que se filtre:",
	"Se desató la telenovela en la esquina; atendé este chisme que no tiene desperdicio:",
	"¡Bomba vecinal! Rompemos el secreto de sumario barrial con esta primicia exclusiva:",
	"Conventillo de alto voltaje: lo que pasa a espaldas de todo el mundo y recién ahora nos enteramos:",
	"¡Agarrate que esto quema! Crónica prohibida del barrio que te va a dejar recalculando:",
)

LEAD_INS_UNKNOWN: tuple[str, ...] = (
	"Atenti a lo que compartimos en el aire de La Rockola.",
	"Pará la oreja a lo que llega a la transmisión.",
	"Seguimos rodando y te dejamos este mensaje en el dial.",
	"Mirá lo que tenemos para vos en este momento.",
	"Un mensaje que llega navegando por la frecuencia.",
)

LEAD_INS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
	"fortuna": LEAD_INS_FORTUNA,
	"aviso": LEAD_INS_AVISOS,
	"oyentes": LEAD_INS_OYENTES,
	"alerta_criolla": LEAD_INS_ALERTAS,
	"chismes": LEAD_INS_CHISMES,
	"novela": LEAD_INS_NOVELA,
	"unknown": LEAD_INS_UNKNOWN,
}

RADIO_LEAD_INS: tuple[str, ...] = (
	LEAD_INS_FORTUNA
	+ LEAD_INS_AVISOS
	+ LEAD_INS_OYENTES
	+ LEAD_INS_ALERTAS
	+ LEAD_INS_CHISMES
	+ LEAD_INS_NOVELA
	+ LEAD_INS_UNKNOWN
)

RADIO_OUTROS: tuple[str, ...] = (
	"Dejamos de parlotear y que hable el bajo. ¡Mandale play!",
	"Acomodá el lomo en la orilla que este tema arranca al palo.",
	"Menos charla y más cumbia. ¡Cambiame la música!",
	"¡Subile al parlante antes de que nos tape la marea!",
	"Se viene un clásico de aquellos... ¡hacete un espacio y bailá!",
	"Frenamos la charla pero la música no para. ¡Escuchate esto!",
	"¡Seguimos con más música!",
	"¡Que no decaiga!",
	"¡Mandale play que esto sigue!",
	"¡Metemos la próxima canción al toque!",
	"¡Seguimos de joda en La Rockola!",
	"¡Acomodate que se viene un temazo!",
	"¡Un carpinchazo de tema para vos; mandale play!",
	"Tranqui en el agua, mate en mano... ¡a disfrutar lo que viene!",
	"¡Al pelo el ritmo; seguimos con todo en La Rockola!",
	"Posta, qué temazo se viene ahora; no te muevas de ahí.",
	"¡Basta de cháchara y que reviente el parche! ¡Mandale play!",
	"¡Subile dos rayitas al volumen que este tema te levanta de la reposera!",
	"¡Agarrate fuerte de la borda que se viene un temazo al palo!",
	"¡A sacudirse el barro de las patas y meterle baile con esto que suena!",
	"¡Largá el remo un minuto y mandate a la pista con esta canción!",
	"¡Este tema te saca la fiaca de un tirón! ¡Dale gas!",
	"¡Temazo de aquellos para escuchar con la ventanilla baja y el viento en la cara!",
	"¡Dejate llevar por el compás que {momento} pide fiesta en la orilla!",
	"¡Volumen al mango que los carpinchos quieren cumbia!",
	"Silencio en el bajo. Que hable la música.",
	"Directo al hueso: temazo que entra sin pedir permiso.",
	"Sin rodeos. Subí el volumen.",
	"Interferencia momentánea superada... dejate llevar por la melodía.",
	"¡Acomodá el parlante mirando al río y disfrutá de este cañonazo musical!",
	# Presentando el "Próximo Tema"
	"Y ahora, un temazo que te va a hacer mover los muebles del living. ¡Ajustate los cinturones porque se viene un clásico de clásicos!",
	"Abrimos el arcón de los recuerdos en la Rockola. Subile el volumen a la radio, que este tema te va a hacer viajar en el tiempo.",
	"¿Querías ritmo? Tomá ritmo. A partir de este momento, se prohíbe quedarse sentado. ¡Que suene la música en la Rockola!",
	# Cierre de tanda / Separadores cortos
	"Pausa publicitaria en la mente, pero la música sigue acá. Estás en la Rockola.",
	"¡Suficiente cháchara por ahora! Subile dos rayitas al parlante y disfrutá este temazo que se viene.",
	"Se acaba la charla en la cabina pero empieza el baile del otro lado. ¡Mandale play nomás!",
	"Cambiamos de ritmo sin doblar la esquina y nos metemos de lleno en el próximo temazo. ¡Mandale play que la mezcla no frena!",
	# "¡Para Maru que nos escucha desde casa, te deseamos que tengas un buen día! ¡Un carpinchazo de tema para vos; cambiame la música!",
)

OUTROS_CHISMES: tuple[str, ...] = (
	"Bueno, cortamos con el conventillo antes de que nos manden una carta documento desde la madriguera. ¡Mandale play a la música!",
	"Suficiente puterío de humedal por hoy, que los carpinchos se ponen nerviosos. ¡Subile al parlante y que tape los murmullos!",
	"Dejamos los trapitos al sol por un rato y volvemos a lo que nos une: ¡metele ritmo y cumbia de la buena!",
	"¡Basta de chismes y a bailar que la música no juzga a nadie! ¡Mandale play nomás!",
	"Guardamos la lengua en remojo por un rato y que hable el bajo. ¡Que siga la fiesta en La Rockola!",
	"Tapamos el puterío de la orilla con tremendo temazo. ¡Subile dos rayitas al volumen!",
)

OUTROS_NOVELA: tuple[str, ...] = (
	"Bueno, tapamos el conventillo con una buena cumbia antes de que caiga el escribano. ¡Mandale play!",
	"Cortamos la novela por acá que se nos enfría el agua del mate. ¡Subile al parlante y a bailar!",
	"Mucho puterío por hoy, muchachos; que hable la música que es la única que no miente. ¡Meté tema!",
	"Bajamos el telón de este capítulo antes de que se arme batalla campal en la esquina. ¡Que suene ese temazo!",
	"Dejamos a los vecinos resolviendo sus quilombos y nosotros a lo nuestro: ¡música bien al palo!",
	"¡Basta de ventilar secretos ajenos! Cambiame la música que la pista está que arde.",
	"Cerramos la persiana del radiopasillo por este bloque; ¡a mover el esqueleto con lo que viene!",
)

OUTROS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
	"chismes": OUTROS_CHISMES,
	"novela": OUTROS_NOVELA,
}

RADIO_OUTROS_DJ: tuple[str, ...] = (
	"No dejaron nada en la fila, pero no pasa nada: el DJ Bara toma el control de las bandejas y te manda esta joyita.",
	"Se vació la lista, pero entra el DJ Bara a tirar magia en la consola. ¡A ver con qué temazo nos sorprende!",
	"Nadie eligió tema, así que dejamos la cabina en manos del DJ Bara. ¡Bailá con lo que eligió!",
	"Tranqui que la música no para: cuando la cola se queda vacía, el DJ Bara se pone la diez y musicaliza el humedal.",
	"Se terminaron los pedidos de la gente, pero el DJ Bara ya tiene preparada la próxima bomba en las bandejas. ¡Escuchate esto!",
	"Bolsillos vacíos en la cola de temas, pero el DJ Bara no te deja a pata nunca: ¡metió mano en la batea y sacó este cañonazo!",
	"Como nadie pidió nada, le dimos vía libre al DJ Bara para que haga de las suyas en la consola. ¡Subile al parlante!",
	"¡Paso al DJ Bara! Cuando la audiencia no pide, él manda música de la buena. ¡A bailar con esto que viene!",
)

RADIO_OUTROS_PAUSE: tuple[str, ...] = (
	"Hacemos una pausita en la orilla para calentar el agua del mate y enseguida volvemos con más música.",
	"Clavamos los remos un ratito porque pidieron pausa en la consola. Cuando quieras, le damos play de nuevo.",
	"Ponemos el freno de mano un toque en La Rockola. Acomodá los tantos y mandale play cuando estés listo.",
	"Pausa pedida en la madriguera: dejamos el próximo tema preparado en la gatera para cuando quieras seguir.",
	"Frenamos la pelota un instante para renovar la yerba. La música queda en pausa esperándote.",
	"Bajamos la palanca un ratito por pedido de la audiencia. ¡A la vuelta seguimos con todo en La Rockola!",
	"Nos tomamos un respiro corto en la barranca. Cuando le des play de nuevo, seguimos bailando.",
	"Queda la consola en pausa como pidieron. Andá tranquilo que los carpinchos te cuidan el lugar.",
)

RADIO_OUTROS_BREAK: tuple[str, ...] = (
	"Se nos secó la fila de temas por ahora, así que los carpinchos nos tomamos un recreo en la laguna hasta que elijan más música.",
	"Llegamos al final de la lista en La Rockola. Cerramos el micrófono un ratito; cuando quieran más ritmo, tiren otro tema a la cola.",
	"No quedaron más canciones en la gatera, che. Nos vamos a flotar un rato al arroyo hasta que alguien ponga otra ficha.",
	"Hasta acá llegó la fila de hoy. Dejamos la consola descansando a la sombra del sauce; sumá unos temas cuando quieras seguir.",
	"Se acabó el repertorio de la cola, compadre. Hacemos un alto en la orilla y volvemos apenas carguen más música.",
	"Último tema de la lista cumplido. Los locutores nos vamos a cebar unos amargos; ¡agregá canciones cuando quieras que acá estamos!",
	"Bolsillos vacíos de canciones por este rato en La Rockola. Nos tomamos un descanso en el juncal hasta la próxima tanda.",
	"Se terminó la fila de reproducción, gente linda. Apagamos los parlantes por un ratito, pero el micrófono queda listo para cuando vuelvan.",
)


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

HOUR_NAMES: tuple[str, ...] = (
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
)

MINUTE_SEGMENTS: tuple[str, ...] = (
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
)

# ---------------------------------------------------------------------------

WEATHER_LEAD_INS: tuple[str, ...] = (
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
)

WEATHER_TEMPLATES: tuple[str, ...] = (
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
)

PASES_A_CLIMA: tuple[str, ...] = (
	"Che {cohost}, asomate al bañado y decime si viene el pampero.",
	"{cohost}, ¿cómo está la temperatura para meter panzada al río?",
	"Tirame la data del cielo, {cohost}, que se me están enfriando las patas.",
	"Decime qué onda afuera, {cohost}, ¿sale mate caliente o tereré?",
	"A ver {vocativo} {cohost}, cantame cómo pinta la mano meteorológica.",
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
	"Cantame los números del clima {cohost}, que {momento} está tan pesada que ni los mosquitos vuelan.",
	"¿Cómo viene la mano con el cielo {cohost}, sale sol para secar el cuero o preparamos el piloto?",
	"{cohost}, {vocativo} de cabina, ¿cómo pinta el tiempo para los que andan navegando la cuenca?",
)

RADIO_HANDOFFS: tuple[str, ...] = (
	"¿Cómo viene la mano afuera, che?",
	"Contame qué dice el servicio meteorológico.",
	"¿Qué tenemos en el pronóstico para hoy?",
	"Tirate esa data de la laguna.",
	"Pará que quiero saber qué dice el oráculo.",
	"¿Qué nos espera en el cielo, {vocativo}?",
	"Tirame el parte meteorológico carpincho.",
)

REACCIONES_CLIMA: dict[str, tuple[str, ...]] = {
	"calor": (
		"¡Mamita querida, qué calorón para estar en el agua todo el día!",
		"¡Hermoso para un chapuzón en la laguna con tereré!",
		"¡Pesadito el calor! No te olvides el protector solar.",
		"¡Está para quedarse a la sombra tomando mates fríos!",
		"¡Qué solazo! A buscar la sombrita del ceibo urgente.",
	),
	"frio": (
		"¡Fresquito para poncho! Metan más leña al fuego.",
		"¡Qué frescor, {vocativo}! Salen esos mates bien calientes.",
		"¡Está para invernar abajo de la paja brava!",
		"¡Se vino el frío de golpe! A cuidar las orejas.",
		"¡Pucha que está fresco! Lindo para unas tortas fritas.",
	),
	"lluvia": (
		"¡Clima soñado de lluvia para andar chapoteando en el agua!",
		"¡Qué hermosura de agua! La laguna nos sonríe.",
		"¡Se viene el agua nomás! A disfrutar del olorcito a tierra mojada.",
		"¡Al pelo la lluvia para meter siesta carpincha!",
		"¡Chaparrón a la vista! El río va a estar una pinturita.",
	),
	"agradable": (
		"¡Una pinturita de día para andar al aire libre!",
		"¡Joya total! El clima ideal para unos amargos en la orilla.",
		"¡Ni frío ni calor, qué más querés para pasarla bomba!",
		"¡Clima perfecto, {vocativo}! A disfrutarlo a pleno.",
		"¡Está de diez afuera! Ni una queja podemos meter.",
	),
}

REACCIONES_FORTUNA: tuple[str, ...] = (
	"¡Olvídate! Mejor explicado, imposible.",
	"¡Uh, qué bárbaro! Me dejó recalculando.",
	"Tal cual, {vocativo}... no le saques ni una coma.",
	"¡Mamita querida! Metiste el dedo en la llaga.",
	"Naaa, qué momento. Piel de carpincho se me puso.",
	"Tranqui, fiera... que no cunda el pánico en el pajonal.",
	"¡Qué personaje! Firmo abajo.",
	"¡Ja! Qué sabio el oráculo.",
	"¡Tal cual, {vocativo}! La pura verdad.",
	"¡Qué lo tiró! Sabiduría pura de la laguna.",
	"¡Amén! Más claro, echale agua.",
	"¡Posta! Tomá nota de esa.",
	"¡Ojo al piojo! No tiene desperdicio.",
	"¡Una joyita de reflexión!",
	"¡Mirá vos! Justo lo que hacía falta escuchar.",
	"¡Palabra santa! A guardarla en el corazón.",
	"¡De una! Nada más que agregar.",
	"¡Clarito como agua de arroyo en bajante!",
	"¡Naaa, qué {filosofo} de bañado tenemos hoy!",
	"¡Aplaudo de pie con las dos patas delanteras!",
	"¡Esa frase te acomoda las ideas de una sola cebada!",
	"¡Una obra de arte! Ni un poeta del Delta lo decía mejor.",
	"¡Totalmente! Guardalo en un frasco de mermelada y no lo pierdas.",
	"¡Qué profundidad criolla! Me quedé sin palabras, {vocativo}.",
	"¡Eso no fue un consejo, fue una caricia al alma!",
	"¡Para ponerlo en un cartelito de madera en la entrada del rancho!",
	"¡Posta pura! Al que no le guste, que vaya a rumiar pasto amargo.",
)

REACCIONES_AVISOS: tuple[str, ...] = (
	"¡Buen dato para los vecinos de la zona!",
	"Excelente servicio a la comunidad, como siempre en La Rockola.",
	"A tenerlo muy en cuenta la muchachada de la orilla.",
	"Ojo al piojo los que anden por ahí, tomen nota.",
	"¡Comercio y comunidad de primera en el humedal!",
	"¡Qué gran servicio! Siempre atentos a lo que pasa en el pago.",
	"Dato clave para no quedarse a pata en el río.",
)

REACCIONES_OYENTES: tuple[str, ...] = (
	"¡Un abrazo gigante para toda esa linda gente que hace el aguante!",
	"¡Qué temazo que pidieron, ya mismo se lo mandamos al aire!",
	"¡Saludos a la barra y gracias por acompañarnos siempre!",
	"¡Al pelo ese mensaje, aguante la audiencia carpincha!",
	"¡Música y mate para todos ellos, que se sientan como en casa!",
	"¡Gente laburadora y de primera sintonizando La Rockola!",
	"¡Un saludo cariñoso para toda la muchachada que escucha!",
)

REACCIONES_ALERTAS: tuple[str, ...] = (
	"¡Qué lo tiró, che! Prendan el espiral y cierren las ventanas.",
	"¡Mamita querida, qué plaga brava! Vayan a refugiarse en la cueva.",
	"¡Terrible situación! Aguanten los trapos que ya va a pasar.",
	"¡Uy, qué quilombo allá en las islas, eh!",
	"¡Fuerza a los que andan cruzando ese paso ahora mismo!",
	"¡Qué panorama bravo por allá; un abrazo grande a los isleños!",
	"Que se cuiden los que están en la zona, nosotros les mandamos un abrazo desde la cabina.",
	"¡Mamita querida lo que les toca pasar allá lejos! A tener paciencia y cuidarse.",
	"Mucha fuerza para la gente de la costa que le está haciendo frente a la correntada.",
)

REACCIONES_CHISMES: tuple[str, ...] = (
	"¡Nooo, mirá de lo que me vengo a enterar! ¡Se me cayó un ídolo ribereño!",
	"¡Esa no la tenía ni por asomo! Con razón siempre se hacían los distraídos...",
	"¡Qué jugoso, por favor! Guardame el secreto que esto no puede salir de la cabina.",
	"¡Naaa, qué fuerte! Si esto llega a oídos de los carpinchos de Nordelta se arma la podrida.",
	"¡Qué papelón! Y uno que los tenía por animales serios, pachorrientos y respetables...",
	"¡Me estás cargando! Mirá el semejante secreto que tenían encanutado bajo los camalotes...",
	"¡Paren las rotativas! Con esto le cambiamos la historia a toda la cuenca del Paraná.",
)

REACCIONES_NOVELA: tuple[str, ...] = (
	"¡Naaa, qué novela mexicana! ¡Decime que esto sigue en el próximo bloque!",
	"¡Me vuelvo loco! ¡Esto es más turbio que mate de tres días! ¡Qué conventillo!",
	"¡Paren todo! ¡No me podés tirar esa bomba y quedarte tan pancho en el control!",
	"¡Qué escándalo vecinal! Si Doña Gladys se entera de que sabemos esto, nos clausura la radio.",
	"¡Se pudrió todo en el barrio! Con vecinos así, ¿quién necesita enemigos?",
	"¡Esa sí que no la vi venir! Andá a buscarla al ángulo con semejante revelación.",
	"¡Qué bochorno, por favor! Mirá la doble vida que se mandaban y nosotros sin enterarnos.",
	"¡Esto es cine total! ¡Qué radioteatro nos estamos armando en plena cabina!",
)

REACCIONES_UNKNOWN: tuple[str, ...] = (
	"¡Clarito como el agua de la orilla!",
	"¡Tal cual, ni más ni menos!",
	"¡Así se habla en el litoral!",
	"¡Impecable, mensaje recibido!",
	"¡Directo y al pie, como tiene que ser!",
)

REACCIONES_BY_CATEGORY: dict[str, tuple[str, ...]] = {
	"fortuna": REACCIONES_FORTUNA,
	"aviso": REACCIONES_AVISOS,
	"oyentes": REACCIONES_OYENTES,
	"alerta_criolla": REACCIONES_ALERTAS,
	"chismes": REACCIONES_CHISMES,
	"novela": REACCIONES_NOVELA,
	"unknown": REACCIONES_UNKNOWN,
}

RADIO_REACTIONS: tuple[str, ...] = (
	"¡Qué lo tiró, che!",
	"Mirá vos, qué momento.",
	"Lindo momento para unos buenos mates.",
	"Una pinturita.",
	"Totalmente, {vocativo}.",
	"Tal cual, fiera.",
	"¡Qué temazo metiste!",
	"La posta pura.",
	"¡Ojo al piojo!",
	"Así se habla en el pago.",
	"¡Qué pedazo de tema, por favor!",
	"Ese solo te afloja hasta las junturas.",
	"¡Inolvidable! Para escucharlo en loop todo el domingo.",
	"¡Qué ritmo sabroso, {vocativo}!",
	"Te deja con el corazón saltando como boga en la red.",
	"¡Una locura total! Música de la buena.",
	"Ese tema te levanta cualquier día nublado.",
	"¡Qué swing ribereño metió esa banda!",
)

# ---------------------------------------------------------------------------


def get_lead_ins_for_category(category: str) -> tuple[str, ...]:
	"""Devuelve los lead-ins pertinentes a la categoría del segmento."""
	return LEAD_INS_BY_CATEGORY.get(category, LEAD_INS_UNKNOWN)


def get_reactions_for_category(category: str) -> tuple[str, ...]:
	"""Devuelve las reacciones de cabina pertinentes a la categoría del segmento."""
	return REACCIONES_BY_CATEGORY.get(category, REACCIONES_UNKNOWN)


def get_outros_for_category(category: str, outro_mode: str = "continue") -> tuple[str, ...]:
	"""Devuelve el banco de cierres pertinentes a la categoría o según el modo de salida."""
	if outro_mode == "pause":
		return RADIO_OUTROS_PAUSE
	if outro_mode == "break":
		return RADIO_OUTROS_BREAK
	if outro_mode == "dj":
		return RADIO_OUTROS_DJ
	if category == "chismes":
		return OUTROS_CHISMES
	if category == "novela":
		return OUTROS_NOVELA
	return OUTROS_BY_CATEGORY.get(category, RADIO_OUTROS)


def get_outros_for_mode(outro_mode: str = "continue") -> tuple[str, ...]:
	"""Devuelve el banco de cierres radiales acorde al modo ('continue', 'pause', 'break' o 'dj')."""
	if outro_mode == "pause":
		return RADIO_OUTROS_PAUSE
	if outro_mode == "break":
		return RADIO_OUTROS_BREAK
	if outro_mode == "dj":
		return RADIO_OUTROS_DJ
	return RADIO_OUTROS
