"""
Bancos de frases de la telenovela vecinal y radioteatro del pago chico.
"""

from __future__ import annotations

NOVELA_VECINAL: tuple[str, ...] = (
	"Dicen que Don Anselmo no le habla a Doña Gladys desde el baile de primavera del 98, pero todas las mañanas le compra el diario en el almacén y le deja vuelto de más a propósito.",
	"El mecánico Pocho le cambió cuatro veces los amortiguadores al Renault 12 de Romina en un mes; el auto anda joya, pero el taller queda justo frente a la peluquería.",
	"Doña Gladys instaló tres cámaras de seguridad en el almacén diciendo que es por prevención, pero una apunta directo a la puerta del taller de Pocho y la otra a la quinta de Anselmo.",
	"El Gordo Walter juró por su madre que la rifa del lechón parroquial fue transparente, pero en la fosa del taller de Pocho encontraron diez talonarios con el mismo número ganador.",
	"El profesor Rodolfo dice que viaja todos los inviernos a un congreso de filosofía en Europa, pero Romina le vio una etiqueta de equipaje de una pensión de San Clemente del Tuyú.",
	"Romina jura que encontró una lata de galletitas oxidada escondida en el foso del taller de Pocho, llena de cartas de amor en manuscrito... y la letra redondita es inconfundiblemente de Doña Gladys.",
	"Don Anselmo amenaza con lotear el terreno baldío de la esquina para poner un criadero de chanchos solo para arruinarle la cancha de paddle que quiere armar el Gordo Walter.",
	"El profesor Rodolfo tiene anotada una deuda de doce cajas de vino en cartón en la libreta de fiado de Doña Gladys, bajo el alias de 'Gastos protocolares de investigación'.",
	"Pocho se apareció en la peluquería de Romina pidiendo turno para hacerse claritos en el pelo, pero se quedó tres horas tomando mate mientras ella le contaba el puterío de las clientas.",
	"Doña Gladys asegura tener el boleto de compraventa del terreno baldío firmado en una servilleta de cantina por el abuelo de Don Anselmo tras una partida de truco de cinco horas.",
	"El Gordo Walter suspendió el clásico de la liga de veteranos a los diez minutos del segundo tiempo porque Don Anselmo le gritó desde el alambrado que sabía con quién cenó el viernes.",
	"Aseguran que Don Anselmo fue a la farmacia a comprar tintura para las canas a las nueve de la noche, y le rogó al farmacéutico que no le comente nada a Gladys ni por todo el oro del mundo.",
	"En el barrio todos sospechan que el profesor Rodolfo no sabe una sola palabra de francés, y que los poemas que le recita a Doña Gladys en el almacén son letras traducidas de Leo Mattioli.",
	"Pocho fue visto a las tres de la madrugada midiendo con cinta métrica el baldío en disputa junto al Gordo Walter, mientras Don Anselmo los relojeaba con una linterna desde el techo.",
	"Romina le confesó a su mejor clienta que Doña Gladys guarda en la trastienda del almacén una foto carnet de Don Anselmo de cuando tenía bigote fino y andaba en motoneta.",
	"El Gordo Walter se comprometió a donar los trofeos del campeonato de bochas, pero cuando abrieron las cajas en el club eran piezas viejas de embrague pulidas que le sobraron a Pocho.",
	"Doña Gladys jura que no le guarda rencor a Don Anselmo, pero cada vez que él pide fiambre le corta la paleta con la máquina al grosor de una baldosa.",
	"El profesor Rodolfo le dejó una propina sospechosamente generosa a Romina en la peluquería para que borre el rumor de que lo vieron cantando cuarteto arriba de una mesa en el buffet del club.",
	"Don Anselmo mandó a soldar un portón de hierro de tres metros en el baldío con la ayuda clandestina de Pocho, a espaldas del Gordo Walter y sin permiso municipal.",
	"Doña Gladys le prohibió la entrada al almacén al Gordo Walter luego de descubrir que el lechón de la rifa que ganó su cuñado en realidad era una pata de ternera congelada que vencía en 2021.",
	"Pocho le armó un silenciador especial al escape del auto de Romina para que no haga ruido cuando pasa despacito por la puerta de la casa de Don Anselmo a deshoras.",
	"El profesor Rodolfo y Don Anselmo casi se van a las manos en la plaza central discutiendo por quién de los dos sacó a bailar primero a Gladys en los carnavales del 84.",
	"Romina descubrió que la llave duplicada del galpón del baldío la tiene el Gordo Walter escondida adentro del botiquín del club deportivo, envuelta en una media de fútbol.",
	"Doña Gladys le bajó la persiana en la cara al profesor Rodolfo cuando este intentó pagarle tres meses de yerba y galletitas de agua con un supuesto poema inédito autografiado.",
	"Don Anselmo jura que es sordo de la oreja izquierda para no contestarle los saludos al Gordo Walter, pero cuando Romina menciona la palabra 'herencia' en la cocina, escucha hasta un suspiro.",
	"En el barrio es un secreto a voces: la caja fuerte que Pocho tiene tapada con lonas en el fondo del taller no guarda guita de autos, guarda el archivo histórico con las quejas vecinales que Doña Gladys fue acumulando durante cuarenta años.",
	"El Gordo Walter fue visto escapando en bicicleta playera del patio de Don Anselmo con dos plantas de tomates cherries bajo el brazo y una pala de punta.",
	"Romina y Pocho fueron fotografiados tomando un helado de dos bochas en la costanera del pueblo vecino, creyendo que nadie los veía... pero en la mesa de al lado estaba Doña Gladys con anteojos oscuros.",
	"El profesor Rodolfo juró que donará su biblioteca personal al pueblo, siempre y cuando Don Anselmo admita públicamente que el truco con el que le ganó la copa de plata en el 92 fue con señas falsas.",
	"Doña Gladys le perdonó la cuenta del fiado a Don Anselmo por primera vez en treinta años, pero le exigió a cambio que le arregle la persiana del almacén y le devuelva la lata de cartas que le sacó a Pocho.",
	"Capítulo 31 de la novela del pago: Don Anselmo descubrió que la carta de amor debajo de la puerta no era para él, sino para el repartidor de garrafas, pero decidió contestarla igual para no quedarse con la espina.",
	"En el episodio de hoy: Gladys citó a Romualdo en la curva de los sauces con un paquete de cartas viejas y una cuchara de albañil, exigiendo explicaciones que llevan veinte años de retraso.",
	"Telenovela comunal: Cacho enfrentó al puestero por el paradero del poncho de vicuña, sin sospechar que el comisario jubilado lo estaba usando de felpudo en la comisaría vieja.",
)
