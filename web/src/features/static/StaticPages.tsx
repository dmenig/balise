import { Link } from 'react-router-dom'
import { DISCLAIMER } from '../../components/DisclaimerStrip'

const ATTRIBUTION_BLOCK =
  'Fonds de carte © OpenStreetMap contributors (ODbL) — Amers et balisage : Shom, 2026 (Licence Ouverte Etalab 2.0) — Mouillages : OpenStreetMap/OpenSeaMap (ODbL) — Marées : Shom — Météo : Open-Meteo (CC-BY 4.0). Ne pas utiliser pour la navigation.'

function Page({ title, children }: { title: string; children: React.ReactNode }): JSX.Element {
  return (
    <article className="mx-auto max-w-2xl p-4">
      <nav className="text-sm">
        <Link to="/" className="underline">
          Carte
        </Link>
      </nav>
      <h1 className="mt-2 text-2xl font-semibold text-sea-900">{title}</h1>
      <div className="prose mt-3 space-y-3 text-sm text-sea-900">{children}</div>
    </article>
  )
}

export function AboutPage(): JSX.Element {
  return (
    <Page title="À propos de Balise">
      <p>
        Balise cartographie le balisage, les bouées de mouillage, les mouillages et les places de
        port de la côte française : profondeur, tailles admissibles, tenue, exposition, tarifs,
        contacts, marées. De quoi choisir son escale.
      </p>
      <p>
        <strong>Cette version n'affiche pas de disponibilité</strong> (place libre ou occupée). Il
        n'existe aucune source publique de disponibilité en France : elle ne se collecte pas, elle
        se fabrique — avec des ports partenaires et une communauté. Afficher une disponibilité vide
        ou fausse serait pire que ne rien afficher : on vous ferait perdre une heure de jour et on
        perdrait votre confiance. En attendant, la carte vous donne le numéro de la capitainerie et
        son canal VHF, à un tap.
      </p>
      <p>{DISCLAIMER}</p>
    </Page>
  )
}

export function ContributePage(): JSX.Element {
  return (
    <Page title="Contribuer">
      <h2 className="text-lg font-semibold">Signaler une erreur</h2>
      <p>
        Sur la fiche d'une place ou d'un port : « Signaler une erreur ». Mauvaise position, bouée
        disparue, tarif ou contact inexact. Un signalement passe en revue, puis devient une
        correction du référentiel — traçable, versionnée, réversible.
      </p>
      <p>
        Ça marche hors ligne : le signalement est mis en file et part à la reconnexion, avec son
        horodatage d'origine. Aucune trace de navigation n'est conservée ; pour une position, seule
        la coordonnée que vous proposez est transmise.
      </p>
      <p>
        Nous ne collectons <strong>pas</strong> de disponibilité (place libre ou occupée) : cette
        version ne l'affiche pas, et afficher une disponibilité fausse serait pire que ne rien
        afficher.
      </p>

      <h2 className="text-lg font-semibold">Vous gérez un port ?</h2>
      <p>
        Vous pouvez revendiquer votre page pour corriger vos contacts, vos tarifs et vos horaires.
        Écrivez-nous à <code>contact@balise.fr</code> depuis l'adresse officielle du port : nous
        vérifions et vous donnons la main sur votre fiche.
      </p>
      <p>
        Si votre logiciel de capitainerie sait exporter l'état de vos places, nous serions ravis
        d'en discuter — c'est un chantier futur, et votre réponse nous dit s'il vaut la peine.
      </p>

      <h2 className="text-lg font-semibold">Améliorer les données à la source</h2>
      <p>
        Le balisage vient du Shom, les mouillages d'OpenStreetMap/OpenSeaMap, les ZMEL de
        data.gouv.fr. Une correction faite en amont profite à tout le monde : nous reversons aussi
        nos corrections à OpenStreetMap.
      </p>
    </Page>
  )
}

export function DataPage(): JSX.Element {
  return (
    <Page title="Données et licences">
      <p>{ATTRIBUTION_BLOCK}</p>
      <ul className="list-inside list-disc">
        <li>Balisage, ports, réglementation, marées : Shom — Licence Ouverte Etalab 2.0.</li>
        <li>Mouillages, marinas, pontons : OpenStreetMap / OpenSeaMap — ODbL 1.0.</li>
        <li>ZMEL et inventaires : data.gouv.fr (DDTM/DREAL) — Licence Ouverte Etalab 2.0.</li>
        <li>Météo et état de la mer : Open-Meteo — CC-BY 4.0.</li>
      </ul>
      <p>
        Nous republions trimestriellement la partie OSM de notre référentiel sous ODbL :{' '}
        <a className="underline" href="/v1/opendata/referential-osm.geojson">
          referential-osm.geojson
        </a>
        . Les données que nous produisons nous-mêmes (signalements de correction) sont stockées
        séparément des tables dérivées d'OSM, pour que le partage à l'identique ODbL reste net.
      </p>
    </Page>
  )
}

export function TermsPage(): JSX.Element {
  return (
    <Page title="Conditions générales d'utilisation">
      <p>{DISCLAIMER}</p>
      <p>
        Balise est une aide à la planification fournie « en l'état ». Les profondeurs affichées sont
        dérivées de sondes cartographiées et de prédictions de marée : ce sont des estimations, pas
        des garanties. Cette version n'affiche aucune disponibilité : la présence d'une place sur la
        carte ne dit rien de sa libération ni de son état. L'état d'un corps-mort et de sa ligne de
        mouillage relève de son gestionnaire — vérifiez toujours votre amarrage.
      </p>
      <h2 className="text-lg font-semibold">Données personnelles</h2>
      <p>
        Votre position n'est jamais stockée sur nos serveurs : elle sert au centrage de la carte,
        côté navigateur. Un signalement de correction conserve l'objet concerné et, si vous le
        proposez, la coordonnée corrigée — jamais votre trace. Les contributions anonymes reposent
        sur un identifiant d'appareil haché (6 mois glissants). Export et suppression :{' '}
        <code>DELETE /v1/me</code>.
      </p>
      <p>
        Les contributions que vous nous confiez sont licenciées en CC-BY-SA 4.0 avec droit de
        sous-licence, afin de pouvoir reverser les corrections à OpenStreetMap.
      </p>
    </Page>
  )
}
