    let token = null;

    const actionsDisponibles = [
        "JOKE", "COMPLIMENT", "DANCE", "PET",
        "DISCUSS", "OBSERVE", "INSULT", "THREATEN"
    ];

    const actionsParCategorie = {
        "NORMAL": 2,
        "MINIBOSS": 3,
        "BOSS": 4
    };

    function afficherMessage(texte)
    {
        document.getElementById("message").textContent = texte;
        setTimeout(() => document.getElementById("message").textContent = "", 3000);
    }

    function mettreAJourActions()
    {
        const categorie = document.getElementById("categorie").value;
        const section = document.getElementById("section-actions");
        const container = document.getElementById("selects-actions");

        if (!categorie)
        {
            section.classList.add("cache");
            return;
        }

        section.classList.remove("cache");
        container.innerHTML = "";

        const nb = actionsParCategorie[categorie];

        for (let i = 1; i <= nb; i++)
        {
            const select = document.createElement("select");
            select.id = "act" + i;

            const optionVide = document.createElement("option");
            optionVide.value = "";
            optionVide.textContent = "-- Action " + i + " --";
            select.appendChild(optionVide);

            for (const action of actionsDisponibles)
            {
                const option = document.createElement("option");
                option.value = action;
                option.textContent = action;
                select.appendChild(option);
            }

            container.appendChild(select);
            container.appendChild(document.createTextNode(" "));
        }

        if (categorie === "NORMAL")
        {
            const hidden3 = document.createElement("input");
            hidden3.type = "hidden";
            hidden3.id = "act3";
            hidden3.value = "-";
            container.appendChild(hidden3);

            const hidden4 = document.createElement("input");
            hidden4.type = "hidden";
            hidden4.id = "act4";
            hidden4.value = "-";
            container.appendChild(hidden4);
        }

        if (categorie === "MINIBOSS")
        {
            const hidden4 = document.createElement("input");
            hidden4.type = "hidden";
            hidden4.id = "act4";
            hidden4.value = "-";
            container.appendChild(hidden4);
        }
    }

    async function ajouterMonstre()
    {
        const categorie = document.getElementById("categorie").value;
        const nom = document.getElementById("nom").value;
        const hp = document.getElementById("hp").value;
        const atk = document.getElementById("atk").value;
        const def = document.getElementById("def").value;
        const mercy = document.getElementById("mercy").value;

        const actions = {};
        for (let i = 1; i <= 4; i++)
        {
            const champ = document.getElementById("act" + i);
            actions["act" + i] = champ ? champ.value : "-";
        }

        const reponse = await fetch("/monstres",
        {
            method: "POST",
            headers:
            {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token
            },
            body: JSON.stringify({ categorie, nom, hp, atk, def, mercy, ...actions })
        });

        const data = await reponse.json();
        afficherMessage(data.message || data.erreur);

        if (reponse.ok)
        {
            document.getElementById("nom").value = "";
            document.getElementById("hp").value = "";
            document.getElementById("atk").value = "";
            document.getElementById("def").value = "";
            document.getElementById("mercy").value = "";
            document.getElementById("categorie").value = "";
            mettreAJourActions();
            chargerMonstres();
        }
    }

    async function login()
    {
        const username = document.getElementById("username").value;
        const password = document.getElementById("password").value;

        const reponse = await fetch("/login",
        {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });

        const data = await reponse.json();

        if (reponse.ok)
        {
            token = data.token;
            document.getElementById("section-login").classList.add("cache");
            document.getElementById("section-admin").classList.remove("cache");
            afficherMessage("Connecte en tant qu'admin");
            chargerMonstres();
        }
        else
        {
            afficherMessage("Identifiants incorrects");
        }
    }

    function deconnexion()
    {
        token = null;
        document.getElementById("section-login").classList.remove("cache");
        document.getElementById("section-admin").classList.add("cache");
        chargerMonstres();
    }

    async function chargerMonstres()
    {
        const reponse = await fetch("/monstres");
        const monstres = await reponse.json();
        const tbody = document.getElementById("liste-monstres");
        tbody.innerHTML = "";

        for (const m of monstres)
        {
            const actions = [m.act1, m.act2, m.act3, m.act4]
                .filter(a => a && a !== "-")
                .join(", ");

            const tr = document.createElement("tr");
            const valeurs = [m.nom, m.categorie, m.hp, m.atk, m.def, m.mercy, actions];

            for (const valeur of valeurs)
            {
                const td = document.createElement("td");
                td.textContent = valeur;
                tr.appendChild(td);
            }

            tr.appendChild(document.createElement("td"));

            if (token)
            {
                const tdBouton = tr.lastElementChild;
                const btn = document.createElement("button");
                btn.textContent = "Supprimer";
                btn.addEventListener("click", () => supprimerMonstre(m.nom));
                tdBouton.appendChild(btn);
            }

            tbody.appendChild(tr);
        }
    }

    async function supprimerMonstre(nom)
    {
        const reponse = await fetch("/monstres/" + encodeURIComponent(nom),
        {
            method: "DELETE",
            headers: { "Authorization": "Bearer " + token }
        });

        const data = await reponse.json();
        afficherMessage(data.message || data.erreur);
        chargerMonstres();
    }

    document.addEventListener("DOMContentLoaded", () => {
        document.getElementById("btn-login").addEventListener("click", login);
        document.getElementById("categorie").addEventListener("change", mettreAJourActions);
        document.getElementById("btn-ajouter").addEventListener("click", ajouterMonstre);
        document.getElementById("btn-deconnexion").addEventListener("click", deconnexion);
        chargerMonstres();
    });

    chargerMonstres();
